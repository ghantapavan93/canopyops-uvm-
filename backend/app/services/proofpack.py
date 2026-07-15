"""Proof Pack assembly — the full auditable package for a record.

Extracted so both the synchronous endpoint (immediate view) and the background
worker (durable, off-request-path generation) build the same artifact.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import domain as m
from app.schemas import AuditOut, EvidenceResult, ObservationOut, ProofPack
from app.services.geo import to_geojson
from app.services.records import build_record, constraint_flags_for


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


def assemble(db: Session, plan_id: str) -> ProofPack | None:
    """Build the ProofPack for a plan, or None if the plan doesn't exist."""
    plan = db.scalars(
        select(m.TreatmentPlan)
        .options(
            selectinload(m.TreatmentPlan.execution).selectinload(m.TreatmentExecution.evidence),
            selectinload(m.TreatmentPlan.observations),
        )
        .where(m.TreatmentPlan.id == plan_id)
    ).first()
    if plan is None:
        return None

    flags = constraint_flags_for(db, [plan.id])
    execution = plan.execution
    audit = db.scalars(
        select(m.AuditEvent)
        .where(m.AuditEvent.entity_id == plan.id)
        .order_by(m.AuditEvent.created_at)
    ).all()

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
