"""Reliability-outcome endpoint — the quantitative "closed ≠ effective" view.

Pairs closed work with the reliability indices UVM is judged by (SAIDI/SAIFI/
CAIDI/CMI) per circuit. Movement is synthetic but driven by real record state
(coverage, evidence, verified status); see services/reliability.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import ReliabilityBoard
from app.services import reliability

router = APIRouter(tags=["reliability"])

_NOTE = (
    "Reliability indices are synthetic and illustrative, but driven by real record "
    "state — treatment coverage, evidence completeness, and verified status — so "
    "closed work that lacks effectiveness shows little SAIDI movement. Not real "
    "outage data; not affiliated with The Davey Tree Expert Company."
)


@router.get("/reliability", response_model=ReliabilityBoard)
def reliability_board(db: Session = Depends(get_db)) -> ReliabilityBoard:
    data = reliability.circuit_reliability(db)
    return ReliabilityBoard(
        generated_at=datetime.now(timezone.utc),
        note=_NOTE,
        rollup=data["rollup"],
        circuits=data["circuits"],
    )
