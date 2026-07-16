"""Background job endpoints — enqueue heavy work and poll its status.

Proof Pack generation and large GeoJSON imports run off the request path via the
durable queue (services/jobs); the request returns a job id immediately and the
worker processes it. Clients poll GET /api/jobs/{id}.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models import domain as m
from app.models import enums as e
from app.schemas import GeoJSONImportJobIn, JobOut
from app.services import jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])

_MANAGER = require_roles(e.Role.PROGRAM_MANAGER)
_ANY_REVIEWER_OR_MANAGER = require_roles(
    e.Role.PROGRAM_MANAGER, e.Role.QUALITY_REVIEWER, e.Role.COMPLIANCE_REVIEWER
)


def _out(job: m.Job) -> JobOut:
    return JobOut(
        id=job.id, type=job.type, status=job.status, attempts=job.attempts,
        max_attempts=job.max_attempts, result=job.result, error=job.error,
        created_at=job.created_at, started_at=job.started_at, finished_at=job.finished_at,
    )


@router.post("/proof-pack/{plan_id}", response_model=JobOut, status_code=202)
def enqueue_proof_pack(
    plan_id: str,
    db: Session = Depends(get_db),
    user: m.User = Depends(_ANY_REVIEWER_OR_MANAGER),
) -> JobOut:
    """Enqueue Proof Pack generation. Returns 202 + a queued job to poll."""
    if db.get(m.TreatmentPlan, plan_id) is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Plan not found"})
    job = jobs.enqueue(db, "proof_pack", {"plan_id": plan_id})
    return _out(job)


@router.post("/geojson-import", response_model=JobOut, status_code=202)
def enqueue_geojson_import(
    payload: GeoJSONImportJobIn,
    db: Session = Depends(get_db),
    user: m.User = Depends(_MANAGER),
) -> JobOut:
    """Enqueue a (potentially large) corridor GeoJSON import off the request path."""
    job = jobs.enqueue(db, "geojson_import", {"features": payload.features, "actor_id": user.id})
    return _out(job)


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: str, db: Session = Depends(get_db),
    user: m.User = Depends(get_current_user),
) -> JobOut:
    job = db.get(m.Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Job not found"})
    return _out(job)


@router.get("", response_model=list[JobOut])
def list_jobs(
    db: Session = Depends(get_db), limit: int = 25,
    user: m.User = Depends(get_current_user),
) -> list[JobOut]:
    rows = db.scalars(
        select(m.Job).order_by(m.Job.created_at.desc()).limit(min(limit, 100))
    ).all()
    return [_out(j) for j in rows]
