"""Outcome verification and record closure — the end of the assurance loop.

Rules that make it defensible:
  * A record cannot be verified until its evidence is complete (a failed upload
    blocks verification — the thesis, enforced server-side).
  * The conclusion is human-authored and evidence-linked; the API never decides
    effectiveness on its own.
  * Status changes follow the state machine (ALLOWED_TRANSITIONS).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.core.security import require_roles
from app.models import domain as m
from app.models import enums as e
from app.schemas import (
    AuditOut,
    ObservationOut,
    ProofPack,
    VerificationIn,
    VerificationResult,
)
from app.services import assurance
from app.services.geo import to_geojson
from app.services.records import build_record, constraint_flags_for

router = APIRouter(prefix="/plans", tags=["verification"])

_REVIEWER = require_roles(e.Role.QUALITY_REVIEWER, e.Role.COMPLIANCE_REVIEWER)
_REVIEWER_OR_MANAGER = require_roles(
    e.Role.QUALITY_REVIEWER, e.Role.COMPLIANCE_REVIEWER, e.Role.PROGRAM_MANAGER
)

_CONCLUSION_TO_STATUS = {
    e.VerificationConclusion.EFFECTIVE: e.TreatmentStatus.EFFECTIVE,
    e.VerificationConclusion.PARTIALLY_EFFECTIVE: e.TreatmentStatus.PARTIALLY_EFFECTIVE,
    e.VerificationConclusion.INEFFECTIVE: e.TreatmentStatus.INEFFECTIVE,
    e.VerificationConclusion.INCONCLUSIVE: e.TreatmentStatus.INCONCLUSIVE,
}


def _load(db: Session, plan_id: str) -> m.TreatmentPlan:
    plan = db.scalars(
        select(m.TreatmentPlan)
        .options(
            selectinload(m.TreatmentPlan.execution).selectinload(
                m.TreatmentExecution.evidence
            ),
            selectinload(m.TreatmentPlan.observations),
        )
        .where(m.TreatmentPlan.id == plan_id)
    ).first()
    if plan is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Plan not found"})
    return plan


def _obs_out(obs: m.VerificationObservation) -> ObservationOut:
    return ObservationOut(
        id=obs.id,
        observed_at=obs.observed_at,
        conclusion=obs.conclusion,
        condition=obs.condition,
        regrowth_observed=obs.regrowth_observed,
        compatible_cover=obs.compatible_cover,
        followup_geometry=to_geojson(obs.followup_geometry),
        reviewer_id=obs.reviewer_id,
    )


@router.post("/{plan_id}/verify", response_model=VerificationResult)
def verify(
    plan_id: str,
    payload: VerificationIn,
    db: Session = Depends(get_db),
    user: m.User = Depends(_REVIEWER),
) -> VerificationResult:
    plan = _load(db, plan_id)

    if plan.status not in (e.TreatmentStatus.AWAITING_VERIFICATION, e.TreatmentStatus.APPLIED):
        raise HTTPException(
            status_code=409,
            detail={"code": "not_verifiable", "message": f"Cannot verify from status '{plan.status.value}'"},
        )

    # Gate: evidence must be complete. A failed upload blocks verification.
    _, complete = assurance.evidence_score(plan)
    if not complete:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "evidence_incomplete",
                "message": "Verification is blocked until required evidence is complete. "
                "Recover the failed upload first.",
            },
        )

    observation = m.VerificationObservation(
        plan_id=plan.id,
        condition=payload.condition,
        regrowth_observed=payload.regrowth_observed,
        compatible_cover=payload.compatible_cover,
        reviewer_id=user.id,
        conclusion=payload.conclusion,
        followup_geometry=from_shape(shape(payload.followup_geometry), srid=4326)
        if payload.followup_geometry else None,
    )
    db.add(observation)

    new_status = _CONCLUSION_TO_STATUS[payload.conclusion]
    before = plan.status
    plan.status = new_status
    db.add(m.AuditEvent(
        actor_id=user.id, action="plan.verified", entity_type="treatment_plan",
        entity_id=plan.id, before={"status": before.value},
        after={"status": new_status.value, "conclusion": payload.conclusion.value},
        reason=payload.condition,
    ))
    db.commit()
    db.refresh(observation)
    return VerificationResult(plan_id=plan.id, status=plan.status, observation=_obs_out(observation))


@router.post("/{plan_id}/plan-followup", response_model=VerificationResult)
def plan_followup(
    plan_id: str,
    db: Session = Depends(get_db),
    user: m.User = Depends(_REVIEWER_OR_MANAGER),
) -> VerificationResult:
    """Commit to a targeted follow-up. Only valid after a non-effective outcome."""
    plan = _load(db, plan_id)
    allowed = {
        e.TreatmentStatus.PARTIALLY_EFFECTIVE,
        e.TreatmentStatus.INEFFECTIVE,
        e.TreatmentStatus.INCONCLUSIVE,
    }
    if plan.status not in allowed:
        raise HTTPException(status_code=409, detail={"code": "bad_state", "message": "No follow-up needed from this state"})
    plan.status = e.TreatmentStatus.FOLLOW_UP_PLANNED
    db.add(m.AuditEvent(
        actor_id=user.id, action="plan.followup_planned", entity_type="treatment_plan",
        entity_id=plan.id, after={"status": plan.status.value},
    ))
    db.commit()
    latest = plan.observations[-1] if plan.observations else None
    return VerificationResult(
        plan_id=plan.id, status=plan.status,
        observation=_obs_out(latest) if latest else ObservationOut(
            id="", observed_at=plan.updated_at, conclusion=None, condition=None,
            regrowth_observed=False, compatible_cover=False, followup_geometry=None,
            reviewer_id=None,
        ),
    )


@router.post("/{plan_id}/close", response_model=VerificationResult)
def close(
    plan_id: str,
    db: Session = Depends(get_db),
    user: m.User = Depends(_REVIEWER_OR_MANAGER),
) -> VerificationResult:
    """Close the record. Only a concluded (or follow-up-planned) record may close."""
    plan = _load(db, plan_id)
    closable = {
        e.TreatmentStatus.EFFECTIVE,
        e.TreatmentStatus.PARTIALLY_EFFECTIVE,
        e.TreatmentStatus.INEFFECTIVE,
        e.TreatmentStatus.INCONCLUSIVE,
        e.TreatmentStatus.FOLLOW_UP_PLANNED,
    }
    if plan.status not in closable:
        raise HTTPException(
            status_code=409,
            detail={"code": "not_closable", "message": f"Cannot close from status '{plan.status.value}'"},
        )
    before = plan.status
    plan.status = e.TreatmentStatus.CLOSED
    db.add(m.AuditEvent(
        actor_id=user.id, action="plan.closed", entity_type="treatment_plan",
        entity_id=plan.id, before={"status": before.value}, after={"status": "closed"},
    ))
    db.commit()
    latest = plan.observations[-1] if plan.observations else None
    return VerificationResult(
        plan_id=plan.id, status=plan.status,
        observation=_obs_out(latest) if latest else ObservationOut(
            id="", observed_at=plan.updated_at, conclusion=None, condition=None,
            regrowth_observed=False, compatible_cover=False, followup_geometry=None,
            reviewer_id=None,
        ),
    )


@router.get("/{plan_id}/proof", response_model=ProofPack)
def proof_pack(plan_id: str, db: Session = Depends(get_db)) -> ProofPack:
    """Assemble the full auditable package for a record."""
    plan = _load(db, plan_id)
    flags = constraint_flags_for(db, [plan.id])
    execution = plan.execution
    audit = db.scalars(
        select(m.AuditEvent)
        .where(m.AuditEvent.entity_id == plan.id)
        .order_by(m.AuditEvent.created_at)
    ).all()
    from app.schemas import EvidenceResult

    return ProofPack(
        record=build_record(plan, flags.get(plan.id, [])),
        planned_geometry=to_geojson(plan.planned_geometry),
        actual_geometry=to_geojson(execution.actual_geometry) if execution else None,
        performed_at=execution.performed_at if execution else None,
        evidence=[
            EvidenceResult(id=ev.id, type=ev.type, upload_status=ev.upload_status)
            for ev in (execution.evidence if execution else [])
        ],
        observations=[_obs_out(o) for o in plan.observations],
        audit_trail=[
            AuditOut(action=a.action, actor_id=a.actor_id, reason=a.reason, created_at=a.created_at)
            for a in audit
        ],
    )
