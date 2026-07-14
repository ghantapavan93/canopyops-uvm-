"""Corridors and environmental constraints — the map's context layers, plus a
live geometry-analysis endpoint used while a manager draws a treatment plan."""
import hashlib
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from shapely.geometry import shape
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import domain as m
from app.models import enums as e
from app.schemas import (
    ConstraintBrief,
    ConstraintOut,
    CorridorOut,
    GeoAnalyzeIn,
    GeoAnalyzeOut,
    ProximityIn,
    ProximityOut,
    ProximityZone,
    ZonesSnapshot,
)
from app.services.geo import to_geojson

router = APIRouter(tags=["geo"])

# Escalating alert levels, worst-last for max().
_LEVEL_RANK = {"clear": 0, "warning": 1, "entered": 2, "breach": 3}


def _proximity_level(
    inside: bool, severity: e.ConstraintSeverity, distance_m: float, warning_m: float
) -> str:
    if inside:
        return "breach" if severity == e.ConstraintSeverity.BLOCKING else "entered"
    if distance_m <= warning_m:
        return "warning"
    return "clear"


def _proximity_action(level: str, category: str, distance_m: float) -> str:
    label = category.replace("_", " ")
    if level == "breach":
        return f"STOP — inside a no-work {label}. Do not proceed; notify compliance immediately."
    if level == "entered":
        return f"Inside {label} — hold work and follow the buffer/habitat-window protocol."
    if level == "warning":
        return f"Approaching {label} ({round(distance_m)} m) — slow down and confirm the boundary."
    return "Clear of protected zones."


@router.post("/geo/analyze", response_model=GeoAnalyzeOut)
def analyze_geometry(payload: GeoAnalyzeIn, db: Session = Depends(get_db)) -> GeoAnalyzeOut:
    """Return the true ground area (acres, via PostGIS geography) and any
    environmental constraints the drawn polygon intersects — so a manager sees
    conflicts before committing the plan."""
    try:
        shp = shape(payload.geometry)
    except Exception:  # noqa: BLE001
        return GeoAnalyzeOut(valid=False, area_acres=0, intersecting_constraints=[], blocking=False)
    if shp.geom_type != "Polygon" or not shp.is_valid or shp.area == 0:
        return GeoAnalyzeOut(valid=False, area_acres=0, intersecting_constraints=[], blocking=False)

    wkt = shp.wkt
    area_m2 = db.execute(
        text("SELECT ST_Area(ST_GeomFromText(:wkt, 4326)::geography)"), {"wkt": wkt}
    ).scalar() or 0.0

    rows = db.scalars(
        select(m.EnvironmentalConstraint).where(
            func.ST_Intersects(
                m.EnvironmentalConstraint.geometry, func.ST_GeomFromText(wkt, 4326)
            )
        )
    ).all()
    constraints = [
        ConstraintBrief(id=c.id, name=c.name, category=c.category, severity=c.severity)
        for c in rows
    ]
    blocking = any(c.severity == e.ConstraintSeverity.BLOCKING for c in rows)
    return GeoAnalyzeOut(
        valid=True,
        area_acres=round(area_m2 / 4046.8564224, 2),
        intersecting_constraints=constraints,
        blocking=blocking,
    )


@router.get("/geo/zones")
def geo_zones(
    if_none_match: str | None = Header(None), db: Session = Depends(get_db)
) -> Response:
    """A versioned, cacheable snapshot of the protected zones. A field device
    stores this so the geofence still works offline (client-side point-in-polygon
    against the same geometry). Content-addressed ``version`` + ETag mean a device
    only re-downloads when the zones actually change (``If-None-Match`` → 304)."""
    rows = db.scalars(select(m.EnvironmentalConstraint)).all()
    zones = [
        ConstraintOut(
            id=c.id, name=c.name, category=c.category, severity=c.severity,
            geometry=to_geojson(c.geometry),
        )
        for c in rows
    ]
    zdump = [z.model_dump(by_alias=True) for z in zones]
    digest = hashlib.sha1(
        json.dumps(zdump, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]
    etag = f'W/"{digest}"'
    if if_none_match and if_none_match.strip() == etag:
        return Response(status_code=304, headers={"ETag": etag})
    body = ZonesSnapshot(version=digest, zones=zones).model_dump(by_alias=True)
    return JSONResponse(body, headers={"ETag": etag, "Cache-Control": "no-cache"})


@router.post("/geo/proximity", response_model=ProximityOut)
def proximity(payload: ProximityIn, db: Session = Depends(get_db)) -> ProximityOut:
    """Geofence check for a crew position: for every protected zone, compute the
    true ground distance (PostGIS ``ST_Distance`` on geography) and whether the
    point is inside (``ST_Contains``), then escalate CLEAR → APPROACHING →
    ENTERED → BREACH. Server-enforced — the alert logic never lives only in the
    UI, so it holds even if a device is compromised or offline-replayed."""
    warning_m = max(0.0, payload.warning_meters)
    sql = text(
        """
        SELECT id, name, category, severity,
               ST_Contains(geometry, pt) AS inside,
               ST_Distance(geometry::geography, pt::geography) AS dist
        FROM environmental_constraint,
             (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326) AS pt) p
        ORDER BY dist ASC
        """
    )
    rows = db.execute(sql, {"lon": payload.lon, "lat": payload.lat}).mappings().all()

    zones: list[ProximityZone] = []
    for r in rows:
        # PostgreSQL enum columns come back as the member NAME (e.g. "WATER_BUFFER");
        # map to the enum so Pydantic serializes the wire value ("water_buffer").
        category = e.ConstraintCategory[r["category"]]
        severity = e.ConstraintSeverity[r["severity"]]
        inside = bool(r["inside"])
        dist = 0.0 if inside else round(float(r["dist"]), 1)
        level = _proximity_level(inside, severity, dist, warning_m)
        zones.append(ProximityZone(
            id=r["id"], name=r["name"], category=category, severity=severity,
            distance_m=dist, inside=inside, level=level,
            action=_proximity_action(level, category.value, dist),
        ))

    overall = max((z.level for z in zones), key=lambda lv: _LEVEL_RANK[lv], default="clear")
    nearest = zones[0] if zones else None
    return ProximityOut(
        lon=payload.lon, lat=payload.lat, warning_meters=warning_m,
        overall_level=overall,
        nearest_name=nearest.name if nearest else None,
        nearest_distance_m=nearest.distance_m if nearest else None,
        zones=zones,
    )


@router.get("/corridors", response_model=list[CorridorOut])
def list_corridors(db: Session = Depends(get_db)) -> list[CorridorOut]:
    corridors = db.scalars(select(m.Corridor)).all()
    return [
        CorridorOut(
            id=c.id,
            circuit_id=c.circuit_id,
            span_label=c.span_label,
            name=c.name,
            voltage_kv=c.voltage_kv,
            centerline=to_geojson(c.centerline),
        )
        for c in corridors
    ]


@router.get("/constraints", response_model=list[ConstraintOut])
def list_constraints(db: Session = Depends(get_db)) -> list[ConstraintOut]:
    rows = db.scalars(select(m.EnvironmentalConstraint)).all()
    return [
        ConstraintOut(
            id=c.id,
            name=c.name,
            category=c.category,
            severity=c.severity,
            geometry=to_geojson(c.geometry),
        )
        for c in rows
    ]
