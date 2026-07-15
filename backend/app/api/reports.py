"""Compliance report — the exportable evidence artifact.

An assurance system exists to produce defensible evidence. This endpoint rolls
the whole program up into one report: attainment, evidence completeness, NERC /
wildfire (HFTD) exposure, and the risk-governance picture (score distribution +
how much of it a certified human has actually signed off). It mirrors the shape
of a utility compliance dashboard (e.g. Davey's ResourceKeeper Insight) — the
front end renders it print-ready so it can be saved as a PDF. Synthetic data.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.risk import score_spans
from app.core.database import get_db
from app.models import domain as m
from app.models import enums as e
from app.schemas import ComplianceReport, ComplianceSpanRow
from app.services import assurance

router = APIRouter(tags=["reports"])

_EXECUTED = {
    e.TreatmentStatus.APPLIED, e.TreatmentStatus.AWAITING_VERIFICATION,
    e.TreatmentStatus.EFFECTIVE, e.TreatmentStatus.PARTIALLY_EFFECTIVE,
    e.TreatmentStatus.INEFFECTIVE, e.TreatmentStatus.INCONCLUSIVE,
    e.TreatmentStatus.FOLLOW_UP_PLANNED, e.TreatmentStatus.CLOSED,
}


@router.get("/reports/compliance", response_model=ComplianceReport)
def compliance_report(db: Session = Depends(get_db)) -> ComplianceReport:
    plans = db.scalars(select(m.TreatmentPlan)).all()
    total = len(plans) or 1
    risk = {s.plan_id: s for s in score_spans(db)}

    hftd = db.execute(text(
        "SELECT COUNT(DISTINCT p.id) FROM treatment_plan p, environmental_constraint c "
        "WHERE c.category = 'HFTD' AND ST_Intersects(p.planned_geometry, c.geometry)"
    )).scalar() or 0

    rows: list[ComplianceSpanRow] = []
    executed = evidence_complete = overdue = closed = 0
    dist = {"critical": 0, "high": 0, "elevated": 0, "low": 0}
    reviewed = unreviewed_hot = 0
    score_sum = 0.0

    for p in plans:
        wo = p.work_order
        corridor = wo.corridor if wo else None
        r = risk.get(p.id)
        _, complete = assurance.evidence_score(p)
        cov = p.execution.coverage_ratio if (p.execution and p.execution.coverage_ratio is not None) else None

        if p.status in _EXECUTED:
            executed += 1
        if complete:
            evidence_complete += 1
        if assurance.is_verification_overdue(p):
            overdue += 1
        if p.status == e.TreatmentStatus.CLOSED:
            closed += 1

        if r:
            dist[r.level] = dist.get(r.level, 0) + 1
            score_sum += r.score
            if r.reviewed:
                reviewed += 1
            elif r.level in ("high", "critical"):
                unreviewed_hot += 1

        rows.append(ComplianceSpanRow(
            work_order_ref=wo.reference if wo else p.id,
            circuit=corridor.circuit_id if corridor else "—",
            span=corridor.span_label if corridor else "—",
            status=p.status.value,
            coverage_pct=round(cov * 100) if cov is not None else None,
            evidence_complete=complete,
            risk_score=r.score if r else 0.0,
            risk_level=r.level if r else "low",
            reviewed=r.reviewed if r else False,
        ))

    rows.sort(key=lambda x: x.risk_score, reverse=True)
    return ComplianceReport(
        generated_at=datetime.now(timezone.utc),
        total_plans=len(plans),
        attainment_pct=round(executed / total * 100, 1),
        evidence_complete_pct=round(evidence_complete / total * 100, 1),
        verification_overdue=overdue,
        closed=closed,
        hftd_intersecting=int(hftd),
        risk_distribution=dist,
        reviewed_pct=round(reviewed / total * 100, 1),
        unreviewed_high_or_critical=unreviewed_hot,
        avg_risk_score=round(score_sum / total, 1),
        spans=rows,
    )
