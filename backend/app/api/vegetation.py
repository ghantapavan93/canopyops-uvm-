"""Vegetation intelligence endpoints — hot-spotting heat + cycle-buster watchlist.

Both make Davey/DRG UVM concepts concrete over the CanopyOps records; see
services/vegetation.py. Scores/geometry are driven by real record state, the
environmental pressures + species assignment are deterministic synthetic.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import CycleBusterBoard, HotspotBoard
from app.services import vegetation

router = APIRouter(prefix="/vegetation", tags=["vegetation"])

_HOTSPOT_NOTE = (
    "Hot-spotting = reactive, repeat work UVM aims to eliminate. Scores blend real "
    "signals (hazard/elevated priority, reworked plans, ineffective outcomes, "
    "treatment effectiveness) with deterministic synthetic encroachment + growth "
    "pressure. Illustrative; not real outage data."
)
_CYCLE_NOTE = (
    "Cycle busters = fast-regrowth species that outrun the trim cycle. Days-to-conflict "
    "projects a species growth rate against remaining MVCD headroom. Species + headroom "
    "are deterministic synthetic; last-treated is the real execution date. Illustrative."
)


@router.get("/hotspots", response_model=HotspotBoard)
def hotspots(db: Session = Depends(get_db)) -> HotspotBoard:
    data = vegetation.hotspots(db)
    return HotspotBoard(
        generated_at=datetime.now(timezone.utc),
        note=_HOTSPOT_NOTE,
        center=data["center"],
        summary=data["summary"],
        hotspots=data["hotspots"],
    )


@router.get("/cycle-busters", response_model=CycleBusterBoard)
def cycle_busters(db: Session = Depends(get_db)) -> CycleBusterBoard:
    data = vegetation.cycle_busters(db)
    return CycleBusterBoard(
        generated_at=datetime.now(timezone.utc),
        note=_CYCLE_NOTE,
        summary=data["summary"],
        spans=data["spans"],
    )
