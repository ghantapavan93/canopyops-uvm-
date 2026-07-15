"""Compliance evidence vault — an auto-assembled documentation dossier.

For a work plan, the vault gathers the whole evidence chain (prescription →
execution → evidence items with integrity → verification → risk sign-off → QA
audit → constraint acknowledgement) and maps it onto the compliance frameworks a
utility answers to (NERC FAC-003 / TVMP, NESC, environmental). Each requirement
is marked satisfied/missing from the underlying records, with an overall
completeness — so a compliance filing is assembled, not hand-collated.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import domain as m
from app.models import enums as e
from app.services import assurance
from app.services.audit import _COVERAGE_MIN, intersecting_plan_ids, latest_audits

# Compliance requirements the vault attests to, mapped to record-derived keys.
FRAMEWORKS = [
    ("NERC FAC-003", "Transmission vegetation work completed & documented", "work_documented"),
    ("TVMP", "Approved treatment prescription on file", "prescription"),
    ("NESC", "Minimum clearance (MVCD) maintained", "clearance"),
    ("Environmental / SWPPP", "Protected zones identified & acknowledged", "constraints"),
    ("QA (checks & balances)", "Independent quality audit passed", "qa"),
]


def _latest_reviews(db: Session) -> dict[str, m.RiskReview]:
    revs = db.scalars(select(m.RiskReview).order_by(m.RiskReview.created_at.asc())).all()
    return {r.plan_id: r for r in revs}


def _components(plan: m.TreatmentPlan, intersects: bool, audit, review, names) -> dict:
    ex = plan.execution
    coverage = ex.coverage_ratio if (ex and ex.coverage_ratio is not None) else None
    ev_score, ev_complete = assurance.evidence_score(plan)
    evidence = []
    if ex:
        for i in ex.evidence:
            stored = i.upload_status == e.UploadStatus.STORED
            evidence.append({
                "type": i.type.value,
                "stored": stored,
                "upload_status": i.upload_status.value,
                "checksum": i.checksum,
                "storage_key": i.storage_key,
                "captured_at": i.captured_at,
            })
    return {
        "coverage": coverage,
        "coverage_ok": coverage is not None and coverage >= _COVERAGE_MIN,
        "evidence_score": ev_score,
        "evidence_complete": ev_complete,
        "evidence": evidence,
        "verified": len(plan.observations) > 0,
        "constraint_intersects": intersects,
        "constraint_ack": bool(ex and ex.constraint_acknowledged),
        "risk_reviewed": review is not None and review.decision != "revoked",
        "risk_reviewer": names.get(review.reviewer_id) if review else None,
        "qa_audited": audit is not None,
        "qa_outcome": audit.outcome if audit else None,
        "qa_auditor": names.get(audit.auditor_id) if audit else None,
    }


def _framework_status(c: dict) -> list[dict]:
    satisfied = {
        "work_documented": c["coverage_ok"] and c["evidence_complete"] and c["verified"],
        "prescription": True,  # a plan always carries a prescription (method + target)
        "clearance": c["coverage_ok"],
        "constraints": (not c["constraint_intersects"]) or c["constraint_ack"],
        "qa": c["qa_outcome"] == "pass",
    }
    detail = {
        "work_documented": "coverage, evidence & verification on file" if satisfied["work_documented"] else "missing coverage, evidence, or verification",
        "prescription": "method + target condition recorded",
        "clearance": f"{round((c['coverage'] or 0) * 100)}% coverage" if c["coverage"] is not None else "no execution recorded",
        "constraints": "no protected zones intersect" if not c["constraint_intersects"] else ("acknowledged in the field" if c["constraint_ack"] else "intersects a zone, not acknowledged"),
        "qa": f"audit outcome: {c['qa_outcome']}" if c["qa_audited"] else "not yet audited",
    }
    return [
        {"code": code, "requirement": req, "satisfied": satisfied[key], "detail": detail[key]}
        for code, req, key in FRAMEWORKS
    ]


def plan_dossier(db: Session, plan: m.TreatmentPlan, intersects: bool, audit, review, names) -> dict:
    wo = plan.work_order
    corridor = wo.corridor if wo else None
    c = _components(plan, intersects, audit, review, names)
    frameworks = _framework_status(c)
    satisfied = sum(1 for f in frameworks if f["satisfied"])
    return {
        "plan_id": plan.id,
        "work_order_ref": wo.reference if wo else plan.id,
        "circuit": corridor.circuit_id if corridor else "—",
        "span": corridor.span_label if corridor else "—",
        "status": plan.status.value,
        "prescription": {
            "method": plan.method_category.value,
            "target_condition": plan.target_condition,
            "required_evidence": [str(t) for t in (plan.required_evidence or [])],
            "revision": plan.revision,
        },
        "components": c,
        "frameworks": frameworks,
        "completeness_pct": round(satisfied / len(frameworks) * 100),
        "satisfied": satisfied,
        "requirements": len(frameworks),
    }


def _load_all(db: Session):
    plans = db.scalars(
        select(m.TreatmentPlan).options(
            selectinload(m.TreatmentPlan.execution).selectinload(m.TreatmentExecution.evidence),
            selectinload(m.TreatmentPlan.observations),
            selectinload(m.TreatmentPlan.work_order).selectinload(m.WorkOrder.corridor),
        )
    ).all()
    intersecting = intersecting_plan_ids(db)
    audits = latest_audits(db)
    reviews = _latest_reviews(db)
    names = {u.id: u.display_name for u in db.scalars(select(m.User)).all()}
    return plans, intersecting, audits, reviews, names


def vault_index(db: Session) -> dict:
    plans, intersecting, audits, reviews, names = _load_all(db)
    rows = [
        plan_dossier(db, p, p.id in intersecting, audits.get(p.id), reviews.get(p.id), names)
        for p in plans
    ]
    rows.sort(key=lambda r: r["completeness_pct"])  # least-complete first (attention)
    total_reqs = sum(r["requirements"] for r in rows) or 1
    total_sat = sum(r["satisfied"] for r in rows)
    summary = {
        "plans": len(rows),
        "fully_compliant": sum(1 for r in rows if r["completeness_pct"] == 100),
        "avg_completeness_pct": round(total_sat / total_reqs * 100),
    }
    return {"summary": summary, "plans": rows}


def one_dossier(db: Session, plan_id: str) -> dict | None:
    plans, intersecting, audits, reviews, names = _load_all(db)
    plan = next((p for p in plans if p.id == plan_id), None)
    if plan is None:
        return None
    return plan_dossier(db, plan, plan.id in intersecting, audits.get(plan.id), reviews.get(plan.id), names)
