"""Work-plan QA audit endpoints — the independent checks-and-balances pass.

The objective criteria are computed server-side from the record (services/audit);
a certified reviewer records the verdict. Persisted append-only + to the audit
trail, RBAC-enforced — a machine surfaces the checks, a person signs the call.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.security import require_roles
from app.models import domain as m
from app.models import enums as e
from app.schemas import AuditIn, AuditQueue, QualityAuditOut
from app.services import audit as audit_svc

router = APIRouter(prefix="/audit", tags=["quality audit"])

_AUDITOR = require_roles(e.Role.QUALITY_REVIEWER, e.Role.COMPLIANCE_REVIEWER)
_VALID_OUTCOMES = {"pass", "conditional", "fail"}

_NOTE = (
    "Independent QA of a sample of closed work against objective criteria "
    "(coverage, evidence, integrity, verification, constraints). The system "
    "surfaces the checks; a certified reviewer records the verdict. Synthetic data."
)


@router.get("/queue", response_model=AuditQueue)
def queue(db: Session = Depends(get_db)) -> AuditQueue:
    data = audit_svc.audit_queue(db)
    return AuditQueue(
        generated_at=datetime.now(timezone.utc),
        note=_NOTE,
        summary=data["summary"],
        items=data["items"],
    )


@router.post("/plans/{plan_id}", response_model=QualityAuditOut)
def record_audit(
    plan_id: str,
    payload: AuditIn,
    db: Session = Depends(get_db),
    user: m.User = Depends(_AUDITOR),
) -> QualityAuditOut:
    """Record a QA verdict on a closed plan. The objective checks are recomputed
    server-side and snapshotted with the verdict (append-only) + an immutable
    audit event. RBAC: only a quality/compliance reviewer may audit."""
    if payload.outcome not in _VALID_OUTCOMES:
        raise HTTPException(status_code=422, detail={
            "code": "invalid_outcome",
            "message": f"outcome must be one of {sorted(_VALID_OUTCOMES)}",
        })

    plan = db.scalars(
        select(m.TreatmentPlan).options(
            selectinload(m.TreatmentPlan.execution).selectinload(m.TreatmentExecution.evidence),
            selectinload(m.TreatmentPlan.observations),
        ).where(m.TreatmentPlan.id == plan_id)
    ).first()
    if plan is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Plan not found"})

    intersects = plan_id in audit_svc.intersecting_plan_ids(db)
    checks, score = audit_svc.compute_checks(plan, intersects)

    record = m.QualityAudit(
        plan_id=plan_id, auditor_id=user.id, outcome=payload.outcome,
        score=score, checks=checks, note=payload.note,
    )
    db.add(record)
    db.add(m.AuditEvent(
        actor_id=user.id, action="workplan.audited", entity_type="treatment_plan",
        entity_id=plan_id, after={"outcome": payload.outcome, "score": score},
        reason=payload.note,
    ))
    db.commit()
    db.refresh(record)
    return QualityAuditOut(
        id=record.id, plan_id=record.plan_id, auditor_id=record.auditor_id,
        auditor_name=user.display_name, outcome=record.outcome, score=record.score,
        checks=record.checks, note=record.note, created_at=record.created_at,
    )


@router.get("/plans/{plan_id}", response_model=list[QualityAuditOut])
def audit_history(plan_id: str, db: Session = Depends(get_db)) -> list[QualityAuditOut]:
    """The full, append-only QA audit history for a plan (newest first)."""
    names = {u.id: u.display_name for u in db.scalars(select(m.User)).all()}
    rows = db.scalars(
        select(m.QualityAudit)
        .where(m.QualityAudit.plan_id == plan_id)
        .order_by(m.QualityAudit.created_at.desc())
    ).all()
    return [
        QualityAuditOut(
            id=r.id, plan_id=r.plan_id, auditor_id=r.auditor_id,
            auditor_name=names.get(r.auditor_id), outcome=r.outcome, score=r.score,
            checks=r.checks, note=r.note, created_at=r.created_at,
        )
        for r in rows
    ]
