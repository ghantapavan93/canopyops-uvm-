"""Field execution + offline sync endpoints.

This is the assurance differentiator. Mobile mutations arriving from an offline
outbox are made safe by two mechanisms:
  * Idempotency-Key  -> a retried submission never creates a duplicate record.
  * plan_revision    -> if the plan moved on server-side while the crew was
                        offline, we return 409 CONFLICT for human resolution,
                        never a silent last-write-wins overwrite.
"""
from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.security import require_roles
from app.models import domain as m
from app.models import enums as e
from app.schemas import (
    ConflictDetail,
    EvidenceResult,
    ExecutionIn,
    ExecutionResult,
)
from app.services import assurance
from app.services.geo import to_shape_or_none

router = APIRouter(prefix="/executions", tags=["executions"])

_CREW_OR_MANAGER = require_roles(e.Role.FIELD_CREW, e.Role.PROGRAM_MANAGER)


def _coverage(planned, actual_geojson: dict) -> float | None:
    planned_shape = to_shape_or_none(planned)
    if planned_shape is None or planned_shape.area == 0:
        return None
    actual = shape(actual_geojson)
    return round(min(planned_shape.intersection(actual).area / planned_shape.area, 1.0), 4)


def _result(execution: m.TreatmentExecution, sync: e.SyncStatus) -> ExecutionResult:
    score, complete = assurance.evidence_score(execution.plan)
    return ExecutionResult(
        id=execution.id,
        plan_id=execution.plan_id,
        plan_status=execution.plan.status,
        coverage_ratio=execution.coverage_ratio,
        evidence_score=score,
        evidence_complete=complete,
        evidence=[
            EvidenceResult(id=ev.id, type=ev.type, upload_status=ev.upload_status)
            for ev in execution.evidence
        ],
        sync_status=sync,
        server_revision=execution.server_revision,
    )


def _record_sync(
    db: Session,
    key: str,
    status: e.SyncStatus,
    entity_id: str | None = None,
    error_code: str | None = None,
    correlation_id: str | None = None,
) -> None:
    """Upsert the sync-attempt row for an idempotency key. Same-key retries
    (including after conflict resolution) update the row instead of colliding
    with the (entity_type, idempotency_key) unique constraint."""
    row = db.scalar(
        select(m.SyncAttempt).where(
            m.SyncAttempt.entity_type == "execution",
            m.SyncAttempt.idempotency_key == key,
        )
    )
    if row:
        row.status = status
        row.entity_id = entity_id or row.entity_id
        row.error_code = error_code
        row.attempt_no += 1
    else:
        db.add(
            m.SyncAttempt(
                entity_type="execution", entity_id=entity_id, idempotency_key=key,
                status=status, error_code=error_code, attempt_no=1,
                correlation_id=correlation_id or "",
            )
        )


def _load_execution(db: Session, execution_id: str) -> m.TreatmentExecution | None:
    return db.scalars(
        select(m.TreatmentExecution)
        .options(
            selectinload(m.TreatmentExecution.evidence),
            selectinload(m.TreatmentExecution.plan),
        )
        .where(m.TreatmentExecution.id == execution_id)
    ).first()


@router.post("", response_model=ExecutionResult)
def submit_execution(
    payload: ExecutionIn,
    request: Request,
    db: Session = Depends(get_db),
    user: m.User = Depends(_CREW_OR_MANAGER),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
) -> ExecutionResult:
    correlation_id = getattr(request.state, "correlation_id", None)

    # 1) Idempotency: a replayed outbox item returns the original result.
    prior = db.scalar(
        select(m.SyncAttempt).where(
            m.SyncAttempt.entity_type == "execution",
            m.SyncAttempt.idempotency_key == idempotency_key,
        )
    )
    if prior and prior.status == e.SyncStatus.ACCEPTED and prior.entity_id:
        existing = _load_execution(db, prior.entity_id)
        if existing:
            return _result(existing, e.SyncStatus.DUPLICATE)

    plan = db.scalars(
        select(m.TreatmentPlan)
        .options(
            selectinload(m.TreatmentPlan.execution).selectinload(
                m.TreatmentExecution.evidence
            )
        )
        .where(m.TreatmentPlan.id == payload.plan_id)
    ).first()
    if plan is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Plan not found"})

    # 2) Revision conflict: the plan changed while the crew was offline.
    if payload.plan_revision != plan.revision:
        _record_sync(
            db, idempotency_key, e.SyncStatus.CONFLICT,
            error_code="revision_conflict", correlation_id=correlation_id,
        )
        db.commit()
        raise HTTPException(
            status_code=409,
            detail=ConflictDetail(
                message="This plan changed on the server while you were offline. "
                "Review the differences before re-submitting.",
                plan_id=plan.id,
                your_revision=payload.plan_revision,
                server_revision=plan.revision,
            ).model_dump(by_alias=True),
        )

    if plan.status == e.TreatmentStatus.CLOSED:
        raise HTTPException(status_code=409, detail={"code": "closed", "message": "Plan is closed"})

    # Validate the drawn geometry server-side (mirrors plan creation) so a
    # malformed or non-polygon shape is a clean 422, not a 500 at insert.
    try:
        actual_geom = shape(payload.actual_geometry)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail={"code": "invalid_geometry", "message": "Unparseable geometry"}) from exc
    if actual_geom.geom_type != "Polygon" or not actual_geom.is_valid or actual_geom.area == 0:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_geometry", "message": "Actual treated area must be a valid, non-self-intersecting polygon"},
        )

    # 3) Create (or replace) the execution record.
    execution = plan.execution or m.TreatmentExecution(plan_id=plan.id)
    execution.actual_geometry = from_shape(actual_geom, srid=4326)
    execution.performed_at = payload.performed_at
    execution.crew_id = user.id
    execution.constraint_acknowledged = payload.constraint_acknowledged
    execution.notes = payload.notes
    execution.coverage_ratio = _coverage(plan.planned_geometry, payload.actual_geometry)
    execution.evidence.clear()
    for item in payload.evidence:
        stored = not item.simulate_upload_failure
        execution.evidence.append(
            m.EvidenceItem(
                type=item.type,
                captured_at=item.captured_at,
                geolocation=from_shape(shape(item.geolocation), srid=4326)
                if item.geolocation else None,
                upload_status=e.UploadStatus.STORED if stored else e.UploadStatus.FAILED,
                storage_key=f"synthetic/{idempotency_key}/{item.type.value}" if stored else None,
                checksum=hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]
                if stored else None,
                value=item.value,
            )
        )
    if plan.execution is None:
        db.add(execution)
    db.flush()  # populate execution.id (UUID default) before referencing it

    # Execution recorded -> plan enters the verification queue.
    plan.status = e.TreatmentStatus.AWAITING_VERIFICATION

    _record_sync(
        db, idempotency_key, e.SyncStatus.ACCEPTED,
        entity_id=execution.id, correlation_id=correlation_id,
    )
    db.add(m.AuditEvent(
        actor_id=user.id, action="execution.submitted", entity_type="treatment_plan",
        entity_id=plan.id, after={"status": plan.status.value, "coverage": execution.coverage_ratio},
        correlation_id=correlation_id,
    ))
    try:
        db.commit()
    except IntegrityError:
        # A concurrent submission with the same Idempotency-Key won the race and
        # inserted the SyncAttempt first (the check at step 1 read before it
        # existed). Honour the idempotency contract: roll back our duplicate work
        # and return the winner's result rather than a 500.
        db.rollback()
        prior = db.scalar(
            select(m.SyncAttempt).where(
                m.SyncAttempt.entity_type == "execution",
                m.SyncAttempt.idempotency_key == idempotency_key,
            )
        )
        if prior and prior.status == e.SyncStatus.ACCEPTED and prior.entity_id:
            existing = _load_execution(db, prior.entity_id)
            if existing:
                return _result(existing, e.SyncStatus.DUPLICATE)
        raise HTTPException(
            status_code=409,
            detail={"code": "duplicate", "message": "This submission is already being processed."},
        )

    execution = _load_execution(db, execution.id)
    return _result(execution, e.SyncStatus.ACCEPTED)


@router.post("/{execution_id}/evidence/{evidence_id}/retry", response_model=ExecutionResult)
def retry_evidence_upload(
    execution_id: str,
    evidence_id: str,
    db: Session = Depends(get_db),
    user: m.User = Depends(_CREW_OR_MANAGER),
) -> ExecutionResult:
    """Retry a failed evidence upload. Recomputes completeness so a recovered
    upload can unblock verification."""
    evidence = db.get(m.EvidenceItem, evidence_id)
    if evidence is None or evidence.execution_id != execution_id:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Evidence not found"})
    evidence.upload_status = e.UploadStatus.STORED
    evidence.storage_key = f"synthetic/retry/{evidence.id}/{evidence.type.value}"
    evidence.checksum = hashlib.sha256(evidence.id.encode()).hexdigest()[:16]
    db.add(m.AuditEvent(
        actor_id=user.id, action="evidence.upload_recovered", entity_type="evidence_item",
        entity_id=evidence.id, after={"upload_status": "stored"},
    ))
    db.commit()
    return _result(_load_execution(db, execution_id), e.SyncStatus.ACCEPTED)
