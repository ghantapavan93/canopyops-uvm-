"""Vegetation intelligence — hot-spotting and cycle busters.

Two Davey/DRG UVM concepts made concrete:

* **Hot-spotting** — the reactive, repeat work UVM programs try to *eliminate*:
  spans that keep re-opening (hazard/elevated priority, reworked plans, or
  ineffective outcomes) instead of being resolved on cycle. We score each span's
  hot-spot intensity so a heat layer can show where reactive spend concentrates.

* **Cycle busters** — fast-regrowth species that outrun the trim cycle and drive
  a mid-cycle conflict with the conductor. We project days-to-conflict from a
  species growth rate against remaining MVCD headroom, so a watchlist can flag
  spans before they breach.

Scores/geometry are grounded in real records (work-order priority, plan
revisions, coverage, evidence, verified status, corridor centerlines); the
environmental pressures and species assignment are deterministic synthetic
(hash-seeded, stable across reloads). Not real biological or outage data.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import domain as m
from app.models import enums as e
from app.services import assurance
from app.services.geo import to_geojson

# Reactive work-order priorities — the hot-spotting signal (vs. planned cycle).
_REACTIVE_PRIORITIES = {e.WorkOrderPriority.HAZARD, e.WorkOrderPriority.ELEVATED}
_CLOSED_STATES = {
    e.TreatmentStatus.APPLIED, e.TreatmentStatus.AWAITING_VERIFICATION,
    e.TreatmentStatus.EFFECTIVE, e.TreatmentStatus.PARTIALLY_EFFECTIVE,
    e.TreatmentStatus.INEFFECTIVE, e.TreatmentStatus.INCONCLUSIVE,
    e.TreatmentStatus.FOLLOW_UP_PLANNED, e.TreatmentStatus.CLOSED,
}

# Fast-to-slow species (real UVM regrowth offenders). ft/yr are typical field
# figures; the fastest are the classic "cycle busters".
_SPECIES = [
    ("Eastern cottonwood", "Populus deltoides", 5.0, True),
    ("Black willow", "Salix nigra", 4.5, True),
    ("Tree-of-heaven", "Ailanthus altissima", 4.0, True),   # invasive
    ("Silver maple", "Acer saccharinum", 3.2, True),
    ("Black locust", "Robinia pseudoacacia", 2.6, False),
    ("Boxelder", "Acer negundo", 2.4, False),
    ("Red maple", "Acer rubrum", 1.8, False),
    ("Northern red oak", "Quercus rubra", 1.4, False),
]
_CYCLE_BUSTER_FT = 3.0  # at/above this annual growth a species breaks the cycle


def _stable(key: str, mod: int) -> int:
    return int(hashlib.sha1(key.encode()).hexdigest(), 16) % mod


def _species_for(corridor_id: str) -> tuple[str, str, float, bool]:
    return _SPECIES[_stable(corridor_id + "species", len(_SPECIES))]


def _plan_effectiveness(plan: m.TreatmentPlan) -> float:
    coverage = plan.execution.coverage_ratio if (plan.execution and plan.execution.coverage_ratio is not None) else 0.0
    evidence, _ = assurance.evidence_score(plan)
    return max(0.0, min(1.0, coverage * evidence))


def _load(db: Session) -> tuple[list[m.Corridor], dict[str, list[m.TreatmentPlan]]]:
    corridors = db.scalars(select(m.Corridor)).all()
    plans = db.scalars(
        select(m.TreatmentPlan).options(
            selectinload(m.TreatmentPlan.execution).selectinload(m.TreatmentExecution.evidence),
            selectinload(m.TreatmentPlan.work_order).selectinload(m.WorkOrder.corridor),
        )
    ).all()
    by_corridor: dict[str, list[m.TreatmentPlan]] = {c.id: [] for c in corridors}
    for p in plans:
        corridor = p.work_order.corridor if p.work_order else None
        if corridor is not None:
            by_corridor.setdefault(corridor.id, []).append(p)
    return corridors, by_corridor


def _tier(score: int) -> str:
    return "hot" if score >= 66 else "elevated" if score >= 40 else "stable"


def hotspots(db: Session) -> dict:
    corridors, by_corridor = _load(db)
    cells: list[dict] = []
    center_lon = center_lat = None

    for corridor in corridors:
        cplans = by_corridor.get(corridor.id, [])
        reactive = sum(
            1 for p in cplans
            if (p.work_order and p.work_order.priority in _REACTIVE_PRIORITIES)
            or p.revision > 1
            or p.status == e.TreatmentStatus.INEFFECTIVE
        )
        planned = len(cplans) - reactive
        total = reactive + planned
        reactive_pct = round(reactive / total * 100) if total else 0

        closed = [p for p in cplans if p.status in _CLOSED_STATES]
        effectiveness = (sum(_plan_effectiveness(p) for p in closed) / len(closed)) if closed else None
        # low effectiveness → work re-opens → hot-spotting. No closed work yet =
        # a neutral, mid gap (unknown), not a free pass.
        eff_gap = round((1 - effectiveness) * 100) if effectiveness is not None else 50

        encroach_pressure = _stable(corridor.circuit_id + corridor.span_label + "enc", 100)
        _, _, growth_ft, _ = _species_for(corridor.id)
        growth_pressure = min(100, round(growth_ft / 6.0 * 100))

        score = round(
            0.40 * reactive_pct + 0.25 * eff_gap + 0.20 * encroach_pressure + 0.15 * growth_pressure
        )
        score = max(0, min(100, score))

        geometry = to_geojson(corridor.centerline)
        if geometry and center_lon is None:
            coords = geometry.get("coordinates") or []
            if coords:
                center_lon, center_lat = coords[len(coords) // 2]

        cells.append({
            "corridor_id": corridor.id,
            "circuit": corridor.circuit_id,
            "span_label": corridor.span_label,
            "voltage_kv": corridor.voltage_kv,
            "geometry": geometry,
            "reactive_repeats": reactive,
            "planned_visits": planned,
            "repeat_rate_pct": reactive_pct,
            "hotspot_score": score,
            "tier": _tier(score),
            "drivers": {
                "reactive_pct": reactive_pct,
                "effectiveness_gap_pct": eff_gap,
                "encroachment_pressure": encroach_pressure,
                "growth_pressure": growth_pressure,
            },
        })

    cells.sort(key=lambda c: -c["hotspot_score"])
    tiers = {"hot": 0, "elevated": 0, "stable": 0}
    for c in cells:
        tiers[c["tier"]] += 1
    summary = {
        "total": len(cells),
        "hot": tiers["hot"],
        "elevated": tiers["elevated"],
        "stable": tiers["stable"],
        "worst_circuit": cells[0]["circuit"] if cells else None,
        "max_score": cells[0]["hotspot_score"] if cells else 0,
    }
    return {
        "center": [center_lon if center_lon is not None else -83.14,
                   center_lat if center_lat is not None else 40.13],
        "summary": summary,
        "hotspots": cells,
    }


def cycle_busters(db: Session) -> dict:
    corridors, by_corridor = _load(db)
    spans: list[dict] = []

    for corridor in corridors:
        common, latin, growth_ft, is_buster = _species_for(corridor.id)
        # Remaining MVCD headroom to the conductor, in feet. Ranges from tight
        # (sub-foot — a span about to breach) to a full cycle's worth.
        headroom_ft = round(0.4 + _stable(corridor.id + "head", 60) / 10.0, 1)  # 0.4..6.3 ft
        growth_per_day = growth_ft / 365.0
        days_to_conflict = int(headroom_ft / growth_per_day) if growth_per_day > 0 else 9999

        cplans = by_corridor.get(corridor.id, [])
        performed = [
            p.execution.performed_at for p in cplans
            if p.execution and p.execution.performed_at is not None
        ]
        last_treated = max(performed) if performed else None

        # Priority relative to the trim cycle: a span that will breach before the
        # next scheduled prune is the essence of a "cycle buster".
        priority = (
            "hazard" if days_to_conflict < 200          # breaches this season → act now
            else "elevated" if days_to_conflict < 400   # within ~a year → schedule mid-cycle
            else "watch"
        )

        spans.append({
            "corridor_id": corridor.id,
            "circuit": corridor.circuit_id,
            "span_label": corridor.span_label,
            "voltage_kv": corridor.voltage_kv,
            "species_common": common,
            "species_latin": latin,
            "growth_ft_per_year": growth_ft,
            "is_cycle_buster": is_buster,
            "mvcd_headroom_ft": headroom_ft,
            "days_to_conflict": days_to_conflict,
            "last_treated": last_treated,
            "priority": priority,
        })

    spans.sort(key=lambda s: s["days_to_conflict"])
    fastest = max(spans, key=lambda s: s["growth_ft_per_year"]) if spans else None
    summary = {
        "watchlist_total": len(spans),
        "cycle_busters": sum(1 for s in spans if s["is_cycle_buster"]),
        "imminent": sum(1 for s in spans if s["days_to_conflict"] < 200),
        "fastest_species": fastest["species_common"] if fastest else None,
        "fastest_growth_ft": fastest["growth_ft_per_year"] if fastest else 0,
    }
    return {"summary": summary, "spans": spans}
