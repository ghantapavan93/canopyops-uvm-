"""Treatment records — the Command Center queue and detail (read side)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.database import get_db
from app.models import domain as m
from app.models import enums as e
from app.schemas import TreatmentRecord
from app.services.records import build_record, constraint_flags_for

router = APIRouter(prefix="/treatments", tags=["treatments"])


def _base_query():
    return select(m.TreatmentPlan).options(
        joinedload(m.TreatmentPlan.work_order).joinedload(m.WorkOrder.corridor),
        selectinload(m.TreatmentPlan.execution).selectinload(
            m.TreatmentExecution.evidence
        ),
    )


@router.get("", response_model=list[TreatmentRecord])
def list_treatments(
    db: Session = Depends(get_db),
    status: list[e.TreatmentStatus] | None = Query(default=None),
    priority: list[e.WorkOrderPriority] | None = Query(default=None),
    q: str | None = Query(default=None),
    bbox: str | None = Query(default=None, description="minLon,minLat,maxLon,maxLat"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[TreatmentRecord]:
    stmt = _base_query()
    if status:
        stmt = stmt.where(m.TreatmentPlan.status.in_(status))
    if priority:
        stmt = stmt.join(m.WorkOrder).where(m.WorkOrder.priority.in_(priority))
    if q:
        like = f"%{q}%"
        stmt = stmt.join(m.WorkOrder).join(m.Corridor).where(
            or_(
                m.WorkOrder.reference.ilike(like),
                m.Corridor.circuit_id.ilike(like),
                m.Corridor.span_label.ilike(like),
                m.Corridor.name.ilike(like),
            )
        )
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = (float(x) for x in bbox.split(","))
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_bbox", "message": "Expected minLon,minLat,maxLon,maxLat"},
            ) from exc
        # Server-side spatial filter — production path for large feature sets.
        stmt = stmt.where(
            func.ST_Intersects(
                m.TreatmentPlan.planned_geometry,
                func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326),
            )
        )

    # Bounded page for scalability — a real program has thousands of spans.
    stmt = stmt.order_by(m.TreatmentPlan.created_at).limit(limit).offset(offset)
    plans = db.scalars(stmt).unique().all()
    flags = constraint_flags_for(db, [p.id for p in plans])
    records = [build_record(p, flags.get(p.id, [])) for p in plans]
    # Rank: exceptions first — overdue, then incomplete evidence, then priority.
    priority_rank = {e.WorkOrderPriority.HAZARD: 0, e.WorkOrderPriority.ELEVATED: 1, e.WorkOrderPriority.ROUTINE: 2}
    records.sort(
        key=lambda r: (
            not r.verification_overdue,
            r.evidence_complete,
            priority_rank.get(r.priority, 3),
        )
    )
    return records


@router.get("/{plan_id}", response_model=TreatmentRecord)
def get_treatment(plan_id: str, db: Session = Depends(get_db)) -> TreatmentRecord:
    plan = db.scalars(_base_query().where(m.TreatmentPlan.id == plan_id)).unique().first()
    if plan is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": "Plan not found"}
        )
    flags = constraint_flags_for(db, [plan.id])
    return build_record(plan, flags.get(plan.id, []))
