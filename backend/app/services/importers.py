"""Bring-your-own-data importers, shared by the sync endpoint and the worker.

A large GeoJSON import should run off the request path, so the corridor-import
core lives here and both `POST /import/corridors` (immediate) and the
`geojson_import` background job call it.
"""
from __future__ import annotations

from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy.orm import Session

from app.models import domain as m


def import_corridors(db: Session, features: list[dict], actor_id: str | None) -> dict:
    """Create a corridor per valid LineString feature. Invalid / non-LineString
    features are skipped (not fatal). Commits, then returns a summary dict."""
    created: list[str] = []
    skipped = 0
    for feature in features:
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
        actor_id=actor_id, action="corridors.imported", entity_type="corridor",
        entity_id="bulk", after={"imported": len(created), "skipped": skipped},
    ))
    db.commit()
    return {"imported": len(created), "skipped": skipped, "corridor_ids": created}
