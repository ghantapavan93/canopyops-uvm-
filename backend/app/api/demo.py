"""Demonstration controls.

A reviewer will click through the console, change state, and then want the story
back. `POST /api/demo/reset` re-runs the synthetic seed so the golden record
(WO-2026-0142) and the rest of the demo data return to a known-good starting
point — no shell access, no docker exec.

Deliberately unauthenticated, like the rest of the demo surface, but ONLY
enabled when the data is synthetic. `DEMO_RESET_ENABLED=false` turns it off, so
this can never become a "wipe the database" button on anything real.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.seed import GOLDEN_REF, seed

router = APIRouter(prefix="/demo", tags=["demo"])
logger = logging.getLogger("canopyops")


@router.post("/reset")
def reset_demo() -> dict:
    """Re-seed the synthetic demonstration data."""
    if not get_settings().demo_reset_enabled:
        raise HTTPException(
            status_code=403,
            detail={"code": "disabled", "message": "Demo reset is disabled in this environment."},
        )
    counts = seed()
    logger.warning("demo_reset", extra={"counts": counts})
    return {
        "reset": True,
        "goldenRecord": GOLDEN_REF,
        "counts": counts,
        "note": "Synthetic demonstration data restored to its starting point.",
    }
