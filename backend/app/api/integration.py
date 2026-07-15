"""Integration surface — ingest real data so the platform can be tested against
an external system's export instead of only synthetic seed data.

`POST /import/corridors` accepts a standard GeoJSON FeatureCollection of ROW
centerlines (LineString) and creates corridor records — a concrete
"bring-your-own-data" path. The same typed contract that powers the synthetic
demo powers a real import; no code path is mocked.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_roles
from app.models import domain as m
from app.models import enums as e
from app.schemas import GeoJSONImport, ImportResult
from app.services import importers

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
    Invalid or non-LineString features are skipped, not fatal. For a large file,
    enqueue a `geojson_import` job (POST /api/jobs/geojson-import) instead.
    """
    r = importers.import_corridors(db, payload.features, user.id)
    return ImportResult(
        imported=r["imported"],
        skipped=r["skipped"],
        corridor_ids=r["corridor_ids"],
        message=f"Imported {r['imported']} corridor(s); skipped {r['skipped']}. "
        "They are now queryable via /api/corridors and render on the map.",
    )
