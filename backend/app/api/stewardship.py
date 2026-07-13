"""Stewardship & compliance — the environmental side of UVM.

Grounded in Davey's real environmental mission (IVM toward compatible vegetation,
Monarch CCAA pollinator habitat, biochar, fuel-intensity ESG targets). Blends
REAL data (IVM method mix, PostGIS constraint intersections) with synthetic,
clearly-labeled sustainability metrics. No endorsement implied.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.overview import _wave
from app.core.database import get_db
from app.models import domain as m
from app.models import enums as e
from app.schemas import (
    ConstraintStatus,
    InsightItem,
    KpiTile,
    NamedSeries,
    StewardshipPayload,
)

router = APIRouter(tags=["stewardship"])

WEEKS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

_METHOD_TONE = {
    e.MethodCategory.MECHANICAL: "primary",
    e.MethodCategory.HERBICIDE: "warn",
    e.MethodCategory.MANUAL: "info",
    e.MethodCategory.BIOLOGICAL: "ok",
    e.MethodCategory.CULTURAL: "neutral",
}

INSIGHTS = [
    ("Compatible vegetation: converting wire zones to low-growing cover", "IVM"),
    ("Monarch CCAA — enrolling ROW acres as pollinator habitat", "Pollinators"),
    ("Biochar from wood waste: circularity + carbon sequestration", "Circularity"),
    ("Selective IVM reduces herbicide load vs. broadcast spraying", "Stewardship"),
    ("Fuel-intensity reduction via fleet telematics toward 2030 target", "Carbon"),
]


@router.get("/stewardship", response_model=StewardshipPayload)
def stewardship(db: Session = Depends(get_db)) -> StewardshipPayload:
    total_plans = db.scalar(select(func.count()).select_from(m.TreatmentPlan)) or 0

    # --- REAL: IVM method mix (group by) ---
    rows = db.execute(
        select(m.TreatmentPlan.method_category, func.count())
        .group_by(m.TreatmentPlan.method_category)
    ).all()
    method_mix = [
        NamedSeries(label=cat.value.capitalize(), tone=_METHOD_TONE.get(cat, "neutral"), points=[float(cnt)])
        for cat, cnt in rows
    ]

    # --- REAL: constraint intersections (PostGIS ST_Intersects) ---
    constraints_rows = db.scalars(select(m.EnvironmentalConstraint)).all()
    constraints: list[ConstraintStatus] = []
    for c in constraints_rows:
        cnt = db.scalar(
            select(func.count())
            .select_from(m.TreatmentPlan)
            .where(func.ST_Intersects(m.TreatmentPlan.planned_geometry, c.geometry))
        ) or 0
        constraints.append(
            ConstraintStatus(
                id=c.id, name=c.name, category=c.category, severity=c.severity,
                intersecting_plans=cnt,
            )
        )

    # --- synthetic, grounded ESG metrics (labeled) ---
    pollinator = _wave(12, 980, 60, 0.6, trend=22)  # habitat acres growing
    compatible_cover = 63.5

    tiles = [
        KpiTile(key="fuel", label="Fuel use / labor-hour", value="-38", unit="%",
                delta=-4.0, delta_good=False, tone="ok", spark=_wave(12, -30, 4, 0.4, -0.8),
                note="vs. 2017 baseline — 2030 target -50% (synthetic)"),
        KpiTile(key="pollinator", label="Pollinator ROW habitat", value="1,240", unit="ac",
                delta=6.2, tone="ok", spark=pollinator,
                note="Monarch CCAA-style enrollment (synthetic)"),
        KpiTile(key="cover", label="Compatible cover established", value=str(compatible_cover), unit="%",
                delta=2.1, tone="primary", spark=_wave(12, 58, 3, 1.0, 0.5),
                note="wire zone converted to low-growing cover"),
        KpiTile(key="biochar", label="Biochar produced", value="142", unit="t",
                delta=9.0, tone="info", spark=_wave(12, 100, 10, 0.8, 4),
                note="wood waste → soil additive (synthetic)"),
    ]

    return StewardshipPayload(
        tiles=tiles,
        method_mix=method_mix,
        compatible_cover_pct=compatible_cover,
        ivm_shift_note="Integrated Vegetation Management favors the minimum effective, "
        "site-appropriate intervention — shifting wire zones toward stable, low-growing "
        "compatible plant communities that resist tall regrowth.",
        weeks=WEEKS,
        pollinator_acres=pollinator,
        constraints=constraints,
        real_plan_count=total_plans,
        insights=[InsightItem(title=t, tag=g) for t, g in INSIGHTS],
    )
