"""Reliability-outcome model — the quantitative form of "closed ≠ effective".

For each circuit we pair the work that was **closed out** with the reliability
**outcome** on that circuit, expressed in the indices UVM is actually judged by
(SAIDI / SAIFI / CAIDI / CMI). The reliability movement is synthetic and
illustrative — but it is *driven by real record state*: a circuit's effectiveness
is computed from actual treatment coverage, evidence completeness, and verified
status, so a circuit that closed lots of work with weak evidence / low coverage
shows little or no SAIDI improvement — surfacing "closed, not effective".

Deterministic (hash-derived baselines; no randomness) so the view is stable
across reloads. Not real outage data; grounded in Davey/DRG UVM framing.

Index definitions (standard):
  * SAIDI — avg outage **minutes** per customer over the period
  * SAIFI — avg **number** of interruptions per customer
  * CAIDI — SAIDI / SAIFI (avg minutes per interruption)
  * CMI   — total customer-minutes interrupted (SAIDI × customers)
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import domain as m
from app.models import enums as e
from app.services import assurance

# Plans considered "closed out" (work executed and booked), matching the
# Overview's completed set — the denominator for "how much did we close?".
_CLOSED_STATES = {
    e.TreatmentStatus.APPLIED, e.TreatmentStatus.AWAITING_VERIFICATION,
    e.TreatmentStatus.EFFECTIVE, e.TreatmentStatus.PARTIALLY_EFFECTIVE,
    e.TreatmentStatus.INEFFECTIVE, e.TreatmentStatus.INCONCLUSIVE,
    e.TreatmentStatus.FOLLOW_UP_PLANNED, e.TreatmentStatus.CLOSED,
}

# How much a closed plan's *outcome* counts toward effectiveness, before the
# evidence/coverage multipliers. A closed-but-graded-ineffective plan is a
# closure that produced no reliability value — the crux of the thesis.
_STATUS_WEIGHT = {
    e.TreatmentStatus.EFFECTIVE: 1.0,
    e.TreatmentStatus.CLOSED: 0.85,
    e.TreatmentStatus.FOLLOW_UP_PLANNED: 0.6,
    e.TreatmentStatus.PARTIALLY_EFFECTIVE: 0.5,
    e.TreatmentStatus.AWAITING_VERIFICATION: 0.4,
    e.TreatmentStatus.INCONCLUSIVE: 0.2,
    e.TreatmentStatus.INEFFECTIVE: 0.0,
}

_EFFECTIVE_THRESHOLD = 0.6  # a closure at/above this is a genuinely effective one


def _stable(key: str, mod: int) -> int:
    """Deterministic pseudo-value in [0, mod) from a string key."""
    return int(hashlib.sha1(key.encode()).hexdigest(), 16) % mod


def _plan_effectiveness(plan: m.TreatmentPlan) -> float:
    """0..1 effectiveness of one closed plan = coverage × evidence × outcome."""
    coverage = plan.execution.coverage_ratio if (plan.execution and plan.execution.coverage_ratio is not None) else 0.0
    evidence, _ = assurance.evidence_score(plan)
    weight = _STATUS_WEIGHT.get(plan.status, 0.3)
    return max(0.0, min(1.0, coverage * evidence * weight))


def circuit_reliability(db: Session) -> dict:
    plans = db.scalars(
        select(m.TreatmentPlan).options(
            selectinload(m.TreatmentPlan.execution).selectinload(m.TreatmentExecution.evidence),
            selectinload(m.TreatmentPlan.work_order).selectinload(m.WorkOrder.corridor),
        )
    ).all()

    # group plans by circuit
    by_circuit: dict[str, list[m.TreatmentPlan]] = {}
    for p in plans:
        corridor = p.work_order.corridor if p.work_order else None
        circuit = corridor.circuit_id if corridor else "UNKNOWN"
        by_circuit.setdefault(circuit, []).append(p)

    circuits: list[dict] = []
    for circuit, cplans in sorted(by_circuit.items()):
        closed_plans = [p for p in cplans if p.status in _CLOSED_STATES]
        closed = len(closed_plans)
        effs = [_plan_effectiveness(p) for p in closed_plans]
        effectiveness = (sum(effs) / closed) if closed else 0.0
        effective_closures = sum(1 for x in effs if x >= _EFFECTIVE_THRESHOLD)
        ineffective_closures = closed - effective_closures

        # deterministic synthetic baselines, in realistic ranges
        customers = 800 + _stable(circuit + "cust", 5200)          # 800..5999
        veg_share = 0.25 + _stable(circuit + "veg", 21) / 100.0    # 0.25..0.45
        saidi_before = 95.0 + _stable(circuit + "saidi", 71)       # 95..165 min
        saifi_before = round(0.9 + _stable(circuit + "saifi", 91) / 100.0, 2)  # 0.90..1.80

        # Effective veg work cuts the vegetation-attributable share of SAIDI;
        # ineffective closures leave latent risk (a small give-back), so a
        # circuit that "closed" work but scored low barely moves.
        ineffective_ratio = (ineffective_closures / closed) if closed else 0.0
        reduction = veg_share * effectiveness * saidi_before
        giveback = veg_share * 0.15 * saidi_before * ineffective_ratio
        saidi_after = round(saidi_before - reduction + giveback, 1)
        saidi_delta = round(saidi_after - saidi_before, 1)          # negative = improved

        saifi_reduction = saifi_before * veg_share * effectiveness
        saifi_giveback = saifi_before * 0.15 * veg_share * ineffective_ratio
        saifi_after = round(max(0.1, saifi_before - saifi_reduction + saifi_giveback), 2)

        caidi_before = round(saidi_before / saifi_before, 1)
        caidi_after = round(saidi_after / saifi_after, 1)
        cmi_before = round(saidi_before * customers)
        cmi_after = round(saidi_after * customers)

        # classify against the thesis
        if closed == 0:
            classification = "pending"
        elif effectiveness >= _EFFECTIVE_THRESHOLD and saidi_delta <= -3.0:
            classification = "effective"
        elif saidi_delta > -1.0:
            classification = "closed_not_effective"
        else:
            classification = "mixed"

        circuits.append({
            "circuit": circuit,
            "customers_served": customers,
            "spans": len(cplans),
            "closed": closed,
            "effective_closures": effective_closures,
            "ineffective_closures": ineffective_closures,
            "effectiveness_pct": round(effectiveness * 100),
            "veg_share_pct": round(veg_share * 100),
            "saidi_before": round(saidi_before, 1),
            "saidi_after": saidi_after,
            "saidi_delta": saidi_delta,
            "saifi_before": saifi_before,
            "saifi_after": saifi_after,
            "caidi_before": caidi_before,
            "caidi_after": caidi_after,
            "cmi_before": cmi_before,
            "cmi_after": cmi_after,
            "classification": classification,
        })

    # program rollup — customer-weighted SAIDI/SAIFI so big circuits count more
    total_customers = sum(c["customers_served"] for c in circuits) or 1
    def _weighted(field: str) -> float:
        return round(sum(c[field] * c["customers_served"] for c in circuits) / total_customers, 1)

    saidi_before_w = _weighted("saidi_before")
    saidi_after_w = _weighted("saidi_after")
    rollup = {
        "customers": total_customers,
        "circuits": len(circuits),
        "closed_total": sum(c["closed"] for c in circuits),
        "effective_total": sum(c["effective_closures"] for c in circuits),
        "ineffective_total": sum(c["ineffective_closures"] for c in circuits),
        "saidi_before": saidi_before_w,
        "saidi_after": saidi_after_w,
        "saidi_delta": round(saidi_after_w - saidi_before_w, 1),
        "saifi_before": _weighted("saifi_before"),
        "saifi_after": _weighted("saifi_after"),
        "cmi_before": sum(c["cmi_before"] for c in circuits),
        "cmi_after": sum(c["cmi_after"] for c in circuits),
        "closed_not_effective_circuits": sum(1 for c in circuits if c["classification"] == "closed_not_effective"),
        "effective_circuits": sum(1 for c in circuits if c["classification"] == "effective"),
    }
    return {"circuits": circuits, "rollup": rollup}
