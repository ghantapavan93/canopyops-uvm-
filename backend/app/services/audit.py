"""Work-plan QA audit — the independent "checks and balances" second pass.

The crew executes and a verifier confirms the outcome; a *separate* certified
reviewer then audits a sample of closed work against objective criteria. This
module computes those objective criteria from the real record (nothing here is
a verdict — the auditor still decides); the API persists the reviewer's call.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.models import domain as m
from app.models import enums as e
from app.services import assurance

# Plans that have been executed and booked — the population eligible for audit.
_AUDITABLE_STATES = {
    e.TreatmentStatus.APPLIED, e.TreatmentStatus.AWAITING_VERIFICATION,
    e.TreatmentStatus.EFFECTIVE, e.TreatmentStatus.PARTIALLY_EFFECTIVE,
    e.TreatmentStatus.INEFFECTIVE, e.TreatmentStatus.INCONCLUSIVE,
    e.TreatmentStatus.FOLLOW_UP_PLANNED, e.TreatmentStatus.CLOSED,
}
_COVERAGE_MIN = 0.90  # MVCD-adequacy threshold for the coverage check


def _stable_unit(seed: str) -> float:
    return (int(hashlib.sha1(seed.encode()).hexdigest(), 16) % 1000) / 1000.0


def intersecting_plan_ids(db: Session) -> set[str]:
    """Plans whose treatment polygon intersects any environmental constraint."""
    return set(db.execute(text(
        "SELECT DISTINCT p.id FROM treatment_plan p, environmental_constraint c "
        "WHERE ST_Intersects(p.planned_geometry, c.geometry)"
    )).scalars().all())


def compute_checks(plan: m.TreatmentPlan, intersects_constraint: bool) -> tuple[list[dict], float]:
    """Objective audit criteria for one plan. Returns (checks, pass_ratio)."""
    ex = plan.execution
    coverage = ex.coverage_ratio if (ex and ex.coverage_ratio is not None) else None
    ev_score, ev_complete = assurance.evidence_score(plan)
    uploads_ok = bool(ex) and all(
        i.upload_status == e.UploadStatus.STORED for i in ex.evidence
    ) if (ex and ex.evidence) else (ev_complete)
    verified = len(plan.observations) > 0
    constraints_ok = (not intersects_constraint) or bool(ex and ex.constraint_acknowledged)

    checks = [
        {
            "key": "coverage", "label": "Coverage meets prescription (≥ 90%)",
            "passed": coverage is not None and coverage >= _COVERAGE_MIN,
            "critical": True,
            "detail": (f"{round(coverage * 100)}% of the planned area treated"
                       if coverage is not None else "no field execution recorded"),
        },
        {
            "key": "evidence", "label": "Evidence set complete",
            "passed": ev_complete, "critical": True,
            "detail": f"{round(ev_score * 100)}% of required evidence stored",
        },
        {
            "key": "integrity", "label": "All evidence uploads stored (no failed)",
            "passed": uploads_ok, "critical": False,
            "detail": "every captured item is stored" if uploads_ok else "a failed/pending upload remains",
        },
        {
            "key": "verification", "label": "Outcome independently verified",
            "passed": verified, "critical": False,
            "detail": f"{len(plan.observations)} verification observation(s)" if verified else "not yet verified",
        },
        {
            "key": "constraints", "label": "Protected zones acknowledged",
            "passed": constraints_ok, "critical": True,
            "detail": ("no protected zones intersect this span" if not intersects_constraint
                       else "constraint acknowledged in the field" if constraints_ok
                       else "intersects a protected zone but was NOT acknowledged"),
        },
    ]
    passed = sum(1 for c in checks if c["passed"])
    return checks, round(passed / len(checks), 4)


def suggested_outcome(score: float, checks: list[dict]) -> str:
    """Decision-support suggestion (the auditor still decides). A failed
    *critical* check caps the suggestion at 'fail'."""
    critical_fail = any(c["critical"] and not c["passed"] for c in checks)
    if critical_fail:
        return "fail"
    return "pass" if score >= 0.999 else "conditional"


def latest_audits(db: Session) -> dict[str, m.QualityAudit]:
    audits = db.scalars(select(m.QualityAudit).order_by(m.QualityAudit.created_at.asc())).all()
    return {a.plan_id: a for a in audits}  # last write per plan wins


def audit_queue(db: Session) -> dict:
    plans = db.scalars(
        select(m.TreatmentPlan).options(
            selectinload(m.TreatmentPlan.execution).selectinload(m.TreatmentExecution.evidence),
            selectinload(m.TreatmentPlan.observations),
            selectinload(m.TreatmentPlan.work_order).selectinload(m.WorkOrder.corridor),
        )
    ).all()
    intersecting = intersecting_plan_ids(db)
    audits = latest_audits(db)
    auditor_names = {u.id: u.display_name for u in db.scalars(select(m.User)).all()}

    items: list[dict] = []
    for p in plans:
        if p.status not in _AUDITABLE_STATES:
            continue
        wo = p.work_order
        corridor = wo.corridor if wo else None
        checks, score = compute_checks(p, p.id in intersecting)
        audit = audits.get(p.id)
        # Deterministic ~40% QA sample so "checks and balances" isn't 100% of work.
        sampled = _stable_unit(p.id + "sample") < 0.4 or audit is not None
        items.append({
            "plan_id": p.id,
            "work_order_ref": wo.reference if wo else p.id,
            "circuit": corridor.circuit_id if corridor else "—",
            "span": corridor.span_label if corridor else "—",
            "status": p.status.value,
            "checks": checks,
            "score": score,
            "suggested_outcome": suggested_outcome(score, checks),
            "sampled": sampled,
            "audited": audit is not None,
            "last_outcome": audit.outcome if audit else None,
            "last_auditor": auditor_names.get(audit.auditor_id) if audit else None,
            "last_audited_at": audit.created_at if audit else None,
        })

    # attention-first: unaudited & sampled, then lowest objective score
    items.sort(key=lambda i: (i["audited"], not i["sampled"], i["score"]))
    total = len(items)
    audited = sum(1 for i in items if i["audited"])
    passed = sum(1 for i in items if i["last_outcome"] == "pass")
    summary = {
        "total": total,
        "sampled": sum(1 for i in items if i["sampled"]),
        "audited": audited,
        "passed": passed,
        "failed": sum(1 for i in items if i["last_outcome"] == "fail"),
        "conditional": sum(1 for i in items if i["last_outcome"] == "conditional"),
        "audit_coverage_pct": round(audited / total * 100) if total else 0,
    }
    return {"summary": summary, "items": items}
