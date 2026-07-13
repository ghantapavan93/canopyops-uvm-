"""Integration surface — ingest real data so the platform can be tested against
an external system's export instead of only synthetic seed data.

`POST /import/corridors` accepts a standard GeoJSON FeatureCollection of ROW
centerlines (LineString) and creates corridor records — a concrete
"bring-your-own-data" path. The same typed contract that powers the synthetic
demo powers a real import; no code path is mocked.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_roles
from app.models import domain as m
from app.models import enums as e
from app.schemas import GeoJSONImport, ImportResult

router = APIRouter(tags=["integration"])


@router.post("/import/corridors", response_model=ImportResult)
def import_corridors(
    payload: GeoJSONImport,
    db: Session = Depends(get_db),
    user: m.User = Depends(require_roles(e.Role.PROGRAM_MANAGER)),
) -> ImportResult:
    """Import ROW corridor centerlines from a GeoJSON FeatureCollection.

    Each LineString feature becomes a corridor. Recognized properties:
    circuitId, spanLabel, name, voltageKv (with snake_case fallbacks).
    Invalid or non-LineString features are skipped, not fatal.
    """
    created: list[str] = []
    skipped = 0
    for feature in payload.features:
        geom = (feature or {}).get("geometry") or {}
        if geom.get("type") != "LineString":
            skipped += 1
            continue
        try:
            shp = shape(geom)
            if shp.is_empty or not shp.is_valid:
                raise ValueError("invalid")
        except Exception:  # noqa: BLE001
            skipped += 1
            continue
        props = feature.get("properties") or {}
        corridor = m.Corridor(
            circuit_id=str(props.get("circuitId") or props.get("circuit_id") or "IMPORT"),
            span_label=str(props.get("spanLabel") or props.get("span_label") or "SPAN"),
            name=str(props.get("name") or "Imported ROW corridor"),
            voltage_kv=int(props.get("voltageKv") or props.get("voltage_kv") or 69),
            centerline=from_shape(shp, srid=4326),
        )
        db.add(corridor)
        db.flush()
        created.append(corridor.id)

    db.add(m.AuditEvent(
        actor_id=user.id, action="corridors.imported", entity_type="corridor",
        entity_id="bulk", after={"imported": len(created), "skipped": skipped},
    ))
    db.commit()
    return ImportResult(
        imported=len(created),
        skipped=skipped,
        corridor_ids=created,
        message=f"Imported {len(created)} corridor(s); skipped {skipped}. "
        "They are now queryable via /api/corridors and render on the map.",
    )
