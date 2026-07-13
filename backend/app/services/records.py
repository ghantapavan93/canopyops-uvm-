"""Assemble TreatmentRecord DTOs from ORM plans + spatial context."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import domain as m
from app.schemas import CorridorRef, TreatmentRecord
from app.services import assurance
from app.services.geo import to_geojson


def constraint_flags_for(db: Session, plan_ids: list[str]) -> dict[str, list]:
    """Which constraint categories intersect each plan polygon.

    Keeps the planned-vs-constraint check in PostGIS (ST_Intersects). Selects
    the enum column directly (SQLAlchemy maps it to the member) and groups in
    Python, avoiding native-enum array_agg parsing pitfalls.
    """
    if not plan_ids:
        return {}
    rows = db.execute(
        select(m.TreatmentPlan.id, m.EnvironmentalConstraint.category)
        .join(
            m.EnvironmentalConstraint,
            func.ST_Intersects(
                m.TreatmentPlan.planned_geometry, m.EnvironmentalConstraint.geometry
            ),
        )
        .where(m.TreatmentPlan.id.in_(plan_ids))
    ).all()
    grouped: dict[str, list] = {}
    for plan_id, category in rows:
        bucket = grouped.setdefault(plan_id, [])
        if category not in bucket:
            bucket.append(category)
    return grouped


def build_record(plan: m.TreatmentPlan, flags: list) -> TreatmentRecord:
    score, complete = assurance.evidence_score(plan)
    wo = plan.work_order
    corridor = wo.corridor
    execution = plan.execution
    return TreatmentRecord(
        plan_id=plan.id,
        work_order_ref=wo.reference,
        corridor=CorridorRef(
            circuit_id=corridor.circuit_id,
            span_label=corridor.span_label,
            name=corridor.name,
        ),
        priority=wo.priority,
        status=plan.status,
        method_category=plan.method_category,
        target_condition=plan.target_condition,
        planned_geometry=to_geojson(plan.planned_geometry),
        actual_geometry=to_geojson(execution.actual_geometry) if execution else None,
        required_evidence=list(plan.required_evidence or []),
        evidence_complete=complete,
        evidence_score=score,
        coverage_ratio=execution.coverage_ratio if execution else None,
        verification_due_at=assurance.verification_due_at(plan),
        verification_overdue=assurance.is_verification_overdue(plan),
        constraint_flags=flags,
        plan_revision=plan.revision,
        updated_at=plan.updated_at or plan.created_at,
    )
