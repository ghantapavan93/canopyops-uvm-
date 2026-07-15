"""Durable background job queue.

A DB-backed queue: heavy work is enqueued as a `job` row and a worker claims it
with ``SELECT ... FOR UPDATE SKIP LOCKED`` (so multiple workers never grab the
same job), runs the handler, and records a terminal state. Failures retry with
exponential backoff up to ``max_attempts``. Jobs survive a process restart —
the queue is the database, not memory.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from opentelemetry import trace
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import SessionLocal
from app.core.tenancy import reset_current_tenant, set_current_tenant
from app.models import domain as m
from app.services import importers, proofpack

logger = logging.getLogger("canopyops")
_tracer = trace.get_tracer("canopyops.worker")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- handlers: type -> callable(db, payload) -> result dict -------------------
def _handle_proof_pack(db: Session, payload: dict) -> dict:
    plan_id = payload.get("plan_id")
    pack = proofpack.assemble(db, plan_id)
    if pack is None:
        raise ValueError(f"plan {plan_id!r} not found")
    return pack.model_dump(by_alias=True, mode="json")


def _handle_geojson_import(db: Session, payload: dict) -> dict:
    features = payload.get("features") or []
    return importers.import_corridors(db, features, payload.get("actor_id"))


HANDLERS = {
    "proof_pack": _handle_proof_pack,
    "geojson_import": _handle_geojson_import,
}


# --- queue operations --------------------------------------------------------
def enqueue(db: Session, job_type: str, payload: dict, max_attempts: int = 3) -> m.Job:
    job = m.Job(type=job_type, payload=payload, status="queued", max_attempts=max_attempts)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim_next(db: Session) -> str | None:
    """Atomically claim the oldest runnable job. Concurrent workers never claim
    the same row thanks to FOR UPDATE SKIP LOCKED."""
    row = db.execute(text(
        """
        UPDATE job
           SET status = 'running', started_at = now(), attempts = attempts + 1, updated_at = now()
         WHERE id = (
             SELECT id FROM job
              WHERE status = 'queued' AND (run_after IS NULL OR run_after <= now())
              ORDER BY created_at
              FOR UPDATE SKIP LOCKED
              LIMIT 1
         )
        RETURNING id
        """
    )).scalar()
    db.commit()
    return row


def process(db: Session, job_id: str) -> None:
    """Run one claimed job to a terminal state (succeeded / failed / requeued)."""
    job = db.get(m.Job, job_id)
    if job is None:
        return
    # Run the job under ITS tenant, so the handler's queries are isolated to the
    # program that enqueued it (the worker itself spans all tenants).
    tenant_token = set_current_tenant(job.tenant_id)
    with _tracer.start_as_current_span(f"job {job.type}") as span:
        span.set_attribute("job.id", job.id)
        span.set_attribute("job.type", job.type)
        span.set_attribute("tenant.id", job.tenant_id or "")
        try:
            handler = HANDLERS.get(job.type)
            if handler is None:
                raise ValueError(f"no handler for job type {job.type!r}")
            result = handler(db, job.payload or {})
            job = db.get(m.Job, job_id)   # re-attach (a handler may have committed)
            job.status = "succeeded"
            job.result = result
            job.error = None
            job.finished_at = _now()
            db.commit()
        except Exception as exc:  # noqa: BLE001 — durable failure handling
            db.rollback()
            job = db.get(m.Job, job_id)
            job.error = str(exc)[:500]
            if job.attempts < job.max_attempts:
                job.status = "queued"
                job.run_after = _now() + timedelta(seconds=min(60, 2 ** job.attempts))
            else:
                job.status = "failed"
                job.finished_at = _now()
            db.commit()
            logger.warning("job_failed", extra={
                "job_id": job.id, "type": job.type, "attempts": job.attempts, "error": job.error,
            })
        finally:
            reset_current_tenant(tenant_token)


def run_once(session_factory: sessionmaker = SessionLocal) -> bool:
    """Claim and process a single job. Returns True if one was processed."""
    with session_factory() as db:
        job_id = claim_next(db)
    if not job_id:
        return False
    with session_factory() as db:
        process(db, job_id)
    return True
