"""Span Risk Intelligence — a deterministic, explainable prioritization engine.

The industry framing for AI in UVM is consistent: it *prioritizes and predicts;
it does not decide*. This endpoint embodies that responsibly — a transparent,
reproducible composite risk score per span from real + synthetic signals, with a
full factor breakdown so a forester can see exactly *why* something ranked high.
No black box, no autonomy: every span carries ``requires_review = true`` and the
recommendation is decision-support only.

Signals combined (weights sum to 100):
  * Encroachment / clearance (28) — from real coverage where a span was worked.
  * Species growth rate (18)      — deterministic per circuit (synthetic).
  * Wildfire exposure / HFTD (22) — real PostGIS intersection with HFTD zones.
  * Terrain / access slope (14)   — from the synthetic DEM along the centerline.
  * Outage history (18)           — deterministic per circuit (synthetic).
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.terrain import elevation, _haversine_m
from app.core.database import get_db
from app.core.security import require_roles
from app.models import domain as m
from app.models import enums as e
from app.schemas import (
    RiskBoard,
    RiskFactor,
    RiskReviewIn,
    RiskReviewOut,
    SpanRisk,
)
from app.services import assurance
from app.services.geo import to_geojson

router = APIRouter(tags=["risk"])

_REVIEWER = require_roles(e.Role.QUALITY_REVIEWER, e.Role.COMPLIANCE_REVIEWER)

WEIGHTS = {"clearance": 28, "growth": 18, "wildfire": 22, "slope": 14, "outage": 18}


def _unit(seed: str) -> float:
    """Deterministic 0..1 from a stable seed (no randomness across reloads)."""
    return (int(hashlib.sha1(seed.encode()).hexdigest(), 16) % 1000) / 1000.0


def _slope_signal(centerline: dict | None) -> tuple[float, float]:
    """Return (0..1 slope signal, slope_pct) along a corridor centerline."""
    if not centerline:
        return 0.0, 0.0
    coords = centerline.get("coordinates") or []
    if len(coords) < 2:
        return 0.0, 0.0
    (lon0, lat0), (lon1, lat1) = coords[0], coords[-1]
    dist = _haversine_m(lon0, lat0, lon1, lat1) or 1.0
    grade = abs(elevation(lon1, lat1) - elevation(lon0, lat0)) / dist * 100.0
    return min(grade / 40.0, 1.0), round(grade, 1)


def _level(score: float) -> str:
    return "critical" if score >= 75 else "high" if score >= 55 else "elevated" if score >= 30 else "low"


def _latest_reviews(db: Session) -> dict[str, m.RiskReview]:
    """Most-recent persisted review per plan (a sign-off or a revocation)."""
    reviews = db.scalars(
        select(m.RiskReview).order_by(m.RiskReview.created_at.asc())
    ).all()
    return {r.plan_id: r for r in reviews}  # last write per plan wins


def score_spans(db: Session) -> list[SpanRisk]:
    from app.core.tenancy import get_current_tenant

    plans = db.scalars(select(m.TreatmentPlan)).all()
    # Raw SQL bypasses the ORM tenant filter, so scope it explicitly.
    tid = get_current_tenant()
    hftd_sql = (
        "SELECT DISTINCT p.id FROM treatment_plan p, environmental_constraint c "
        "WHERE c.category = 'HFTD' AND ST_Intersects(p.planned_geometry, c.geometry)"
    )
    params: dict = {}
    if tid is not None:
        hftd_sql += " AND p.tenant_id = :tid"
        params["tid"] = tid
    hftd_plan_ids = set(db.execute(text(hftd_sql), params).scalars().all())
    reviews = _latest_reviews(db)
    reviewer_names = {u.id: u.display_name for u in db.scalars(select(m.User)).all()}

    out: list[SpanRisk] = []
    for p in plans:
        wo = p.work_order
        corridor = wo.corridor if wo else None
        circuit = corridor.circuit_id if corridor else "—"

        # --- normalized 0..1 signals ---
        cov = p.execution.coverage_ratio if (p.execution and p.execution.coverage_ratio is not None) else None
        clearance = round(1.0 - cov, 3) if cov is not None else 0.6   # unworked span = latent encroachment
        growth = round(_unit(circuit + ":growth"), 3)
        wildfire = 0.9 if p.id in hftd_plan_ids else round(_unit(circuit + ":fire") * 0.4, 3)
        slope_sig, slope_pct = _slope_signal(to_geojson(corridor.centerline) if corridor else None)
        outages_n = int(_unit(circuit + ":out") * 4)                  # 0..3 prior outages
        outage = round(outages_n / 3.0, 3)

        signals = {"clearance": clearance, "growth": growth, "wildfire": wildfire,
                   "slope": slope_sig, "outage": outage}
        notes = {
            "clearance": (f"{round(cov * 100)}% coverage on last pass" if cov is not None
                          else "no field execution yet — latent encroachment"),
            "growth": f"{'fast' if growth > 0.6 else 'moderate' if growth > 0.3 else 'slow'}-growing species mix",
            "wildfire": ("intersects an HFTD zone" if p.id in hftd_plan_ids else "outside mapped HFTD zones"),
            "slope": f"{slope_pct}% grade along the span",
            "outage": f"{outages_n} prior vegetation-caused outage(s)",
        }

        factors = [
            RiskFactor(name=k, value=signals[k], weight=WEIGHTS[k],
                       contribution=round(WEIGHTS[k] * signals[k], 1), note=notes[k])
            for k in WEIGHTS
        ]
        score = round(sum(f.contribution for f in factors), 1)
        top = max(factors, key=lambda f: f.contribution)
        rec = {
            "clearance": "Schedule a directional prune to restore wire-zone clearance",
            "growth": "Consider a growth-regulator or tighter cycle for this species mix",
            "wildfire": "Prioritize ahead of fire season — HFTD risk-weighted",
            "slope": "Plan access & fall protection for the steep grade before dispatch",
            "outage": "Reliability hot-spot — target to break the outage-repeat pattern",
        }[top.name]

        review = reviews.get(p.id)
        # A revocation reopens the span — the latest review must be an active sign-off.
        active = review is not None and review.decision != "revoked"
        out.append(SpanRisk(
            plan_id=p.id,
            work_order_ref=wo.reference if wo else p.id,
            circuit=circuit,
            span=corridor.span_label if corridor else "—",
            score=score, level=_level(score), factors=factors,
            recommendation=f"{rec} — pending forester review.",
            reviewed=active,
            reviewed_by=reviewer_names.get(review.reviewer_id) if active else None,
            reviewed_at=review.created_at if active else None,
        ))

    out.sort(key=lambda s: s.score, reverse=True)
    return out


@router.get("/risk/spans", response_model=RiskBoard)
def risk_spans(db: Session = Depends(get_db)) -> RiskBoard:
    return RiskBoard(generated_at=datetime.now(timezone.utc), spans=score_spans(db))


@router.post("/risk/spans/{plan_id}/review", response_model=RiskReviewOut)
def review_span(
    plan_id: str,
    payload: RiskReviewIn,
    db: Session = Depends(get_db),
    user: m.User = Depends(_REVIEWER),
) -> RiskReviewOut:
    """A certified reviewer signs off on a span's risk. Persists an append-only
    review record (snapshotting the score they saw) + an immutable audit event —
    turning the human-in-the-loop guardrail into durable evidence. Server-enforced
    RBAC: only a quality/compliance reviewer may sign off; a machine never can."""
    plan = db.get(m.TreatmentPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Span not found"})

    # Snapshot the current score the reviewer is signing against.
    current = next((s for s in score_spans(db) if s.plan_id == plan_id), None)
    score = current.score if current else 0.0
    level = current.level if current else "low"

    review = m.RiskReview(
        plan_id=plan_id, reviewer_id=user.id, score=score, level=level,
        decision=payload.decision, note=payload.note,
    )
    db.add(review)
    action = "risk.review_revoked" if payload.decision == "revoked" else "risk.reviewed"
    db.add(m.AuditEvent(
        actor_id=user.id, action=action, entity_type="treatment_plan",
        entity_id=plan_id, after={"score": score, "level": level, "decision": payload.decision},
        reason=payload.note,
    ))
    db.commit()
    db.refresh(review)
    return RiskReviewOut(
        id=review.id, plan_id=review.plan_id, reviewer_id=review.reviewer_id,
        reviewer_name=user.display_name, score=review.score, level=review.level,
        decision=review.decision, note=review.note, created_at=review.created_at,
    )


@router.get("/risk/spans/{plan_id}/reviews", response_model=list[RiskReviewOut])
def span_review_history(plan_id: str, db: Session = Depends(get_db)) -> list[RiskReviewOut]:
    """The full, append-only review history for a span (newest first) — the
    durable evidence trail of every sign-off and revocation."""
    names = {u.id: u.display_name for u in db.scalars(select(m.User)).all()}
    revs = db.scalars(
        select(m.RiskReview)
        .where(m.RiskReview.plan_id == plan_id)
        .order_by(m.RiskReview.created_at.desc())
    ).all()
    return [
        RiskReviewOut(
            id=r.id, plan_id=r.plan_id, reviewer_id=r.reviewer_id,
            reviewer_name=names.get(r.reviewer_id), score=r.score, level=r.level,
            decision=r.decision, note=r.note, created_at=r.created_at,
        )
        for r in revs
    ]
