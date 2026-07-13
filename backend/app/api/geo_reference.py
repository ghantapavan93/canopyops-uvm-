"""Corridors and environmental constraints — the map's context layers, plus a
live geometry-analysis endpoint used while a manager draws a treatment plan."""
from fastapi import APIRouter, Depends, HTTPException
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
)
from app.services.geo import to_geojson

router = APIRouter(tags=["geo"])


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
