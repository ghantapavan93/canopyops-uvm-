"""Liveness / readiness endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness — process is up."""
    return {"status": "ok", "service": "canopyops-api"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    """Readiness — DB reachable and PostGIS available."""
    postgis = db.execute(text("SELECT PostGIS_Version()")).scalar()
    return {"status": "ready", "postgis": postgis}
