"""Program Overview — an executive UVM dashboard.

Blends REAL signals from the seeded records (plan counts, evidence completeness,
constraint intersections) with DETERMINISTIC synthetic program-scale trends so
the view is stable across reloads. Every number is synthetic/illustrative and
labeled as such in the UI. Domain framing and terminology are grounded in
Davey's public UVM materials; no real data or endorsement is implied.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import domain as m
from app.models import enums as e
from app.schemas import (
    ActivityItem,
    EncroachmentMap,
    InsightItem,
    KpiTile,
    NamedSeries,
    OverviewPayload,
    RegionCell,
    StatusCount,
)
from app.services import assurance

router = APIRouter(tags=["overview"])

# Synthetic sandbox origin (matches the seed grid; NOT a real location).
LON0, LAT0 = -83.20, 40.10

# Synthetic service districts for the encroachment choropleth (4x2 grid).
DISTRICTS = [
    ("North Ridge", "CKT-8840"), ("Mill Branch", "CKT-8841"),
    ("Cedar Hollow", "CKT-8842"), ("Coastal Reach", "CKT-8843"),
    ("Foothill Gap", "CKT-8844"), ("Junction", "CKT-8845"),
    ("Lakeside", "CKT-8846"), ("Summit", "CKT-8847"),
]

# Selectable time windows. Each: (n points, x-labels, human label).
PERIODS: dict[str, tuple[int, list[str], str]] = {
    "ytd": (
        12,
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "Year to date",
    ),
    "quarter": (6, ["Wk 1", "Wk 2", "Wk 3", "Wk 4", "Wk 5", "Wk 6"], "This quarter"),
    "cycle": (5, ["Yr 1", "Yr 2", "Yr 3", "Yr 4", "Yr 5"], "5-year cycle"),
}


def _wave(n: int, base: float, amp: float, phase: float, trend: float = 0.0) -> list[float]:
    """Deterministic smooth series — no randomness, stable across reloads."""
    return [
        round(base + amp * math.sin((i / n) * math.pi * 3 + phase) + trend * i, 2)
        for i in range(n)
    ]


# Illustrative topic feed grounded in Davey/DRG real service lines & programs
# (not our content; framing only).
INSIGHTS = [
    ("Balancing infrastructure and ecological conservation in utility ROWs", "IVM"),
    ("Reliability-focused work planning to eliminate cycle busters", "Reliability"),
    ("Monarch CCAA: turning ROW corridors into pollinator habitat", "Stewardship"),
    ("HFTD clearance strategy ahead of fire season", "Wildfire"),
    ("Storm & disaster recovery: mobilizing line-clearance crews across states", "Resilience"),
    ("TGR solutions — slowing regrowth near conductors", "IVM"),
    ("Joint-use pole audits & double-wood removal", "Asset mgmt"),
    ("LiDAR + ML smart inventory for grow-in / fall-in risk", "Technology"),
]


@router.get("/overview", response_model=OverviewPayload)
def overview(period: str = "ytd", db: Session = Depends(get_db)) -> OverviewPayload:
    n, labels, plabel = PERIODS.get(period, PERIODS["ytd"])

    # --- real signals from the seeded records ---
    plans = db.scalars(select(m.TreatmentPlan)).all()
    total = len(plans) or 1
    completed_states = {
        e.TreatmentStatus.APPLIED, e.TreatmentStatus.AWAITING_VERIFICATION,
        e.TreatmentStatus.EFFECTIVE, e.TreatmentStatus.PARTIALLY_EFFECTIVE,
        e.TreatmentStatus.INEFFECTIVE, e.TreatmentStatus.INCONCLUSIVE,
        e.TreatmentStatus.FOLLOW_UP_PLANNED, e.TreatmentStatus.CLOSED,
    }
    real_completed = sum(1 for p in plans if p.status in completed_states)
    real_evidence = [assurance.evidence_score(p)[0] for p in plans]
    avg_evidence = round(sum(real_evidence) / total * 100)
    hftd_ct = db.scalar(
        select(func.count()).select_from(m.EnvironmentalConstraint).where(
            m.EnvironmentalConstraint.category == e.ConstraintCategory.HFTD
        )
    ) or 0

    # --- REAL lifecycle distribution: one SQL GROUP BY over live plan state.
    # This drives the interactive lifecycle bar and shifts as work moves.
    status_rows = db.execute(
        select(m.TreatmentPlan.status, func.count())
        .group_by(m.TreatmentPlan.status)
    ).all()
    by_status = {s: c for s, c in status_rows}
    # Canonical lifecycle order (only surface states that actually exist).
    order = [
        e.TreatmentStatus.DRAFT, e.TreatmentStatus.SCHEDULED,
        e.TreatmentStatus.IN_PROGRESS, e.TreatmentStatus.APPLIED,
        e.TreatmentStatus.AWAITING_VERIFICATION, e.TreatmentStatus.FOLLOW_UP_PLANNED,
        e.TreatmentStatus.EFFECTIVE, e.TreatmentStatus.PARTIALLY_EFFECTIVE,
        e.TreatmentStatus.INEFFECTIVE, e.TreatmentStatus.INCONCLUSIVE,
        e.TreatmentStatus.CLOSED,
    ]
    status_distribution = [
        StatusCount(status=s, count=by_status[s])
        for s in order if by_status.get(s)
    ]

    # REAL attainment = share of plans past the "applied" line (work executed).
    real_attainment = round(real_completed / total * 100, 1)

    # --- REAL activity feed: the audit trail is immutable business history, so
    # this reflects exactly what has happened, newest first. Updates live.
    audit_rows = db.scalars(
        select(m.AuditEvent).order_by(m.AuditEvent.created_at.desc()).limit(8)
    ).all()
    recent_activity = [
        ActivityItem(action=a.action, at=a.created_at, entity_id=a.entity_id)
        for a in audit_rows
    ]

    # --- deterministic synthetic program-scale trends ---
    planned = _wave(n, 240, 26, 0.4, trend=1.2)
    completed = [round(p * (0.86 + 0.01 * i / n), 1) for i, p in enumerate(planned)]
    attainment_pct = round(sum(completed) / sum(planned) * 100, 1)
    mvcd = _wave(n, 96.5, 1.6, 1.1, trend=0.05)
    saidi = _wave(n, 34, 7, 2.2, trend=-0.6)  # tree-caused SAIDI trending down (good)
    regrowth = _wave(n, 7.5, 2.2, 0.2, trend=-0.08)
    cost = _wave(n, 1180, 90, 0.9, trend=-4)
    prod = _wave(n, 3.2, 0.5, 1.6, trend=-0.02)

    tiles = [
        KpiTile(key="attainment", label="Work-plan attainment", value=str(real_attainment),
                unit="%", delta=2.4, tone="ok", spark=[c / p * 100 for c, p in zip(completed, planned)],
                note=f"Live: {real_completed} of {total} plans executed"),
        KpiTile(key="mvcd", label="MVCD clearance compliance", value=str(round(mvcd[-1], 1)),
                unit="%", delta=0.6, tone="ok", spark=mvcd,
                note="Minimum Vegetation Clearance Distance"),
        KpiTile(key="hftd", label="HFTD risk-weighted completion", value="91.2",
                unit="%", delta=3.1, tone="warn", spark=_wave(n, 88, 3, 0.7, 0.3),
                note="Wildfire high-threat districts prioritized"),
        KpiTile(key="saidi", label="Tree-caused SAIDI", value=str(round(saidi[-1], 1)),
                unit="min", delta=-1.8, delta_good=False, tone="info", spark=saidi,
                note="Lower is better — outage minutes"),
        KpiTile(key="evidence", label="Evidence completeness", value=str(avg_evidence),
                unit="%", delta=None, tone="primary", spark=_wave(n, 82, 6, 1.3, 0.6),
                note=f"Computed from {total} live records"),
        KpiTile(key="spend", label="YTD spend vs budget", value="93.4",
                unit="%", delta=-1.2, delta_good=False, tone="neutral", spark=_wave(n, 90, 4, 0.5, 0.3),
                note="Under budget — synthetic"),
    ]

    return OverviewPayload(
        period_label=f"{plabel} (synthetic)",
        real_plan_count=total,
        generated_at=datetime.now(timezone.utc),
        status_distribution=status_distribution,
        recent_activity=recent_activity,
        tiles=tiles,
        weeks=labels,
        planned_spans=planned,
        completed_spans=completed,
        attainment_pct=attainment_pct,
        cycle_regions=["North", "Central", "Coastal", "Foothill"],
        cycle_mix=[
            NamedSeries(label="Cycle prune", tone="primary", points=[62, 58, 49, 44]),
            NamedSeries(label="Mid-cycle / hot-spot", tone="warn", points=[21, 27, 24, 30]),
            NamedSeries(label="Hazard / target trees", tone="danger", points=[9, 12, 15, 18]),
        ],
        mvcd_pct=round(mvcd[-1], 1),
        hftd_labels=["Tier 1", "Tier 2", "Tier 3 (extreme)"],
        hftd_tiers=[
            NamedSeries(label="Complete", tone="ok", points=[97, 92, 88]),
            NamedSeries(label="Remaining", tone="danger", points=[3, 8, 12]),
        ],
        saidi_points=saidi,
        audit_pass_pct=94.2,
        evidence_complete_pct=avg_evidence,
        regrowth_points=regrowth,
        refusals_pct=4.3,
        quality_breakdown=[
            NamedSeries(label="Evidence complete", tone="ok", points=[float(real_completed)]),
            NamedSeries(label="Partial / in progress", tone="warn", points=[float(max(total - real_completed - 1, 0))]),
            NamedSeries(label="Blocked / refused", tone="danger", points=[1.0]),
        ],
        cost_per_span=cost,
        production_rate=prod,
        insights=[InsightItem(title=t, tag=g) for t, g in INSIGHTS],
    )


@router.get("/encroachments", response_model=EncroachmentMap)
def encroachments() -> EncroachmentMap:
    """Choropleth of vegetation encroachments by synthetic service district.

    Deterministic (index-derived) so the map is stable across reloads. An
    encroachment = a confirmed grow-in/fall-in conflict against the conductor.
    """
    cols, rows = 4, 2
    cell_w, cell_h = 0.12 / cols, 0.06 / rows
    regions: list[RegionCell] = []
    for r in range(rows):
        for c in range(cols):
            i = r * cols + c
            x0 = LON0 + c * cell_w
            y0 = LAT0 + r * cell_h
            enc = 6 + (i * 13 % 44) + c * 4  # deterministic ~6..60
            tier = 3 if enc > 45 else 2 if enc > 26 else 1
            tone = "danger" if enc > 45 else "warn" if enc > 26 else "ok"
            name, circuit = DISTRICTS[i]
            regions.append(
                RegionCell(
                    id=f"D{i + 1}",
                    name=name,
                    circuit=circuit,
                    geometry={
                        "type": "Polygon",
                        "coordinates": [[
                            [round(x0, 5), round(y0, 5)],
                            [round(x0 + cell_w, 5), round(y0, 5)],
                            [round(x0 + cell_w, 5), round(y0 + cell_h, 5)],
                            [round(x0, 5), round(y0 + cell_h, 5)],
                            [round(x0, 5), round(y0, 5)],
                        ]],
                    },
                    encroachments=enc,
                    mvcd_pct=round(99.0 - enc * 0.12, 1),
                    hftd_tier=tier,
                    open_work_orders=2 + (i * 5 % 11),
                    tone=tone,
                )
            )
    return EncroachmentMap(
        regions=regions,
        max_encroachments=max(r.encroachments for r in regions),
        total_encroachments=sum(r.encroachments for r in regions),
        center=[LON0 + 0.06, LAT0 + 0.03],
    )
