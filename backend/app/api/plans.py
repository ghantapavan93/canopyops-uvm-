"""Plan mutations: create a treatment plan (manager), and a synthetic control to
simulate a concurrent server-side plan edit for the offline conflict path."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models import domain as m
from app.models import enums as e
from app.models.domain import _now
from app.schemas import PlanCreate, TreatmentRecord
from app.services.records import build_record, constraint_flags_for

router = APIRouter(prefix="/plans", tags=["plans"])


@router.post("", response_model=TreatmentRecord, status_code=201)
def create_plan(
    payload: PlanCreate,
    db: Session = Depends(get_db),
    user: m.User = Depends(require_roles(e.Role.PROGRAM_MANAGER)),
) -> TreatmentRecord:
    """Manager prescribes a treatment: a work order + an approved plan with a
    drawn GIS polygon, target outcome, required evidence, and a verification
    window. Geometry is validated server-side."""
    corridor = db.scalar(select(m.Corridor).where(m.Corridor.id == payload.corridor_id))
    if corridor is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Corridor not found"})

    try:
        geom = shape(payload.planned_geometry)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail={"code": "invalid_geometry", "message": "Unparseable geometry"}) from exc
    if geom.geom_type != "Polygon" or not geom.is_valid or geom.area == 0:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_geometry", "message": "Planned area must be a valid, non-self-intersecting polygon"},
        )

    count = db.scalar(select(func.count()).select_from(m.WorkOrder)) or 0
    work_order = m.WorkOrder(
        reference=f"WO-2026-{2000 + count}",
        priority=payload.priority,
        corridor_id=corridor.id,
        owner_id=user.id,
        due_at=_now() + timedelta(days=payload.due_in_days),
    )
    db.add(work_order)
    db.flush()

    plan = m.TreatmentPlan(
        work_order_id=work_order.id,
        status=e.TreatmentStatus.SCHEDULED,
        planned_geometry=from_shape(geom, srid=4326),
        target_condition=payload.target_condition,
        method_category=payload.method_category,
        required_evidence=[t.value for t in payload.required_evidence],
        verification_policy={"window_days": payload.verification_window_days, "cycle": payload.cycle},
        owner_id=user.id,
    )
    db.add(plan)
    db.flush()
    db.add(m.AuditEvent(
        actor_id=user.id, action="plan.created", entity_type="treatment_plan",
        entity_id=plan.id, after={"status": plan.status.value, "reference": work_order.reference},
    ))
    db.commit()

    plan = db.scalars(
        select(m.TreatmentPlan)
        .options(
            joinedload(m.TreatmentPlan.work_order).joinedload(m.WorkOrder.corridor),
            selectinload(m.TreatmentPlan.execution).selectinload(m.TreatmentExecution.evidence),
        )
        .where(m.TreatmentPlan.id == plan.id)
    ).first()
    flags = constraint_flags_for(db, [plan.id])
    return build_record(plan, flags.get(plan.id, []))


@router.post("/{plan_id}/bump-revision")
def bump_revision(
    plan_id: str,
    db: Session = Depends(get_db),
    # Synthetic demo control (stands in for a manager editing on another device);
    # any authenticated user may trigger it so the conflict path is one click.
    user: m.User = Depends(get_current_user),
) -> dict:
    """Simulate a manager editing the plan while a crew is offline: increments
    the server revision so the next offline execution sync detects a conflict."""
    plan = db.scalar(select(m.TreatmentPlan).where(m.TreatmentPlan.id == plan_id))
    if plan is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Plan not found"})
    before = plan.revision
    plan.revision += 1
    db.add(m.AuditEvent(
        actor_id=user.id, action="plan.edited", entity_type="treatment_plan",
        entity_id=plan.id, before={"revision": before}, after={"revision": plan.revision},
        reason="Synthetic concurrent edit (conflict demo).",
    ))
    db.commit()
    return {"planId": plan.id, "serverRevision": plan.revision}
