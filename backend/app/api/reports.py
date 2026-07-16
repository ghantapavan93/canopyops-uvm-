"""Compliance report — the exportable evidence artifact.

An assurance system exists to produce defensible evidence. This rolls the program
up into one report: attainment, evidence completeness, NERC / wildfire (HFTD)
exposure, and the risk-governance picture (score distribution + how much a
certified human has actually signed off). Available as JSON (for the print-ready
console page) and as a real, server-generated **PDF** with a fixed letterhead.
Optionally scoped to a single circuit. Synthetic data.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response
from fpdf import FPDF
from fpdf.enums import XPos, YPos
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


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _last_activity(p: m.TreatmentPlan) -> datetime:
    """Most-recent activity date for a plan (field execution, else last update)."""
    if p.execution and p.execution.performed_at:
        return _as_utc(p.execution.performed_at)
    return _as_utc(p.updated_at or p.created_at)


def build_report(
    db: Session,
    circuit: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> ComplianceReport:
    since, until = _as_utc(since), _as_utc(until)
    plans = db.scalars(select(m.TreatmentPlan)).all()
    if circuit:
        plans = [
            p for p in plans
            if p.work_order and p.work_order.corridor
            and p.work_order.corridor.circuit_id == circuit
        ]
    if since or until:
        plans = [
            p for p in plans
            if (since is None or _last_activity(p) >= since)
            and (until is None or _last_activity(p) <= until)
        ]
    total = len(plans) or 1
    risk = {s.plan_id: s for s in score_spans(db)}

    # Raw SQL bypasses the ORM tenant filter, so scope it explicitly (matching
    # risk.py / audit.py) — belt-and-suspenders with Postgres RLS.
    from app.core.tenancy import get_current_tenant
    _tid = get_current_tenant()
    _hftd_sql = (
        "SELECT DISTINCT p.id FROM treatment_plan p, environmental_constraint c "
        "WHERE c.category = 'HFTD' AND ST_Intersects(p.planned_geometry, c.geometry)"
    )
    _params: dict = {}
    if _tid is not None:
        _hftd_sql += " AND p.tenant_id = :tid"
        _params["tid"] = _tid
    hftd_ids = set(db.execute(text(_hftd_sql), _params).scalars().all())

    rows: list[ComplianceSpanRow] = []
    executed = evidence_complete = overdue = closed = hftd = 0
    dist = {"critical": 0, "high": 0, "elevated": 0, "low": 0}
    reviewed = unreviewed_hot = 0
    score_sum = 0.0

    for p in plans:
        wo = p.work_order
        corridor = wo.corridor if wo else None
        r = risk.get(p.id)
        _, complete = assurance.evidence_score(p)
        cov = p.execution.coverage_ratio if (p.execution and p.execution.coverage_ratio is not None) else None

        executed += p.status in _EXECUTED
        evidence_complete += complete
        overdue += assurance.is_verification_overdue(p)
        closed += p.status == e.TreatmentStatus.CLOSED
        hftd += p.id in hftd_ids

        if r:
            dist[r.level] = dist.get(r.level, 0) + 1
            score_sum += r.score
            if r.reviewed:
                reviewed += 1
            elif r.level in ("high", "critical"):
                unreviewed_hot += 1

        rows.append(ComplianceSpanRow(
            work_order_ref=wo.reference if wo else p.id,
            circuit=corridor.circuit_id if corridor else "-",
            span=corridor.span_label if corridor else "-",
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
        hftd_intersecting=hftd,
        risk_distribution=dist,
        reviewed_pct=round(reviewed / total * 100, 1),
        unreviewed_high_or_critical=unreviewed_hot,
        avg_risk_score=round(score_sum / total, 1),
        spans=rows,
    )


@router.get("/reports/compliance", response_model=ComplianceReport)
def compliance_report(
    circuit: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    db: Session = Depends(get_db),
) -> ComplianceReport:
    return build_report(db, circuit, since, until)


# --------------------------------------------------------------------------- #
# Server-generated PDF (fixed letterhead) — a real export, not browser print.  #
# --------------------------------------------------------------------------- #
GREEN = (31, 111, 75)
DARK = (22, 33, 28)
MUTE = (91, 107, 98)
RED = (180, 35, 31)


def _ascii(s: str) -> str:
    """Core PDF fonts are Latin-1 only — keep text safe."""
    return (s or "").encode("latin-1", "replace").decode("latin-1")


class _ReportPDF(FPDF):
    """Letterhead on page 1, a slim running header on continuations, and a
    page-numbered footer — so a large program paginates cleanly."""

    def header(self) -> None:
        if self.page_no() == 1:
            self.set_fill_color(*GREEN)
            self.rect(0, 0, 210, 22, style="F")
            self.set_xy(12, 6)
            self.set_text_color(255, 255, 255)
            self.set_font("Helvetica", "B", 16)
            self.cell(0, 10, "CanopyOps  -  UVM Compliance Report",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_y(26)
        else:
            self.set_fill_color(*GREEN)
            self.rect(0, 0, 210, 11, style="F")
            self.set_xy(12, 3)
            self.set_text_color(255, 255, 255)
            self.set_font("Helvetica", "B", 9)
            self.cell(0, 5, "CanopyOps  -  UVM Compliance Report (continued)",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_y(16)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_text_color(*MUTE)
        self.set_font("Helvetica", "I", 7)
        self.cell(0, 6, _ascii(f"Synthetic data - not a regulatory filing.    Page {self.page_no()}/{{nb}}"),
                  align="C")


def render_pdf(report: ComplianceReport, circuit: str | None, since: datetime | None = None) -> bytes:
    from fpdf.fonts import FontFace

    pdf = _ReportPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_left_margin(12)
    pdf.set_right_margin(12)
    pdf.add_page()

    pdf.set_text_color(*MUTE)
    pdf.set_font("Helvetica", "", 9)
    scope = f"circuit {circuit}" if circuit else "all circuits"
    if since:
        scope += f", activity since {since.strftime('%Y-%m-%d')}"
    stamp = report.generated_at.strftime("%Y-%m-%d %H:%M UTC")
    pdf.cell(0, 5, _ascii(f"Generated {stamp}  -  {report.total_plans} records  -  {scope}"),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "I", 7)
    pdf.multi_cell(0, 4, _ascii(
        "Independent concept - synthetic data. Illustrative summary, not a regulatory filing, "
        "and not affiliated with or endorsed by The Davey Tree Expert Company."))
    pdf.ln(3)

    def section(title: str) -> None:
        pdf.set_text_color(*MUTE)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, _ascii(title.upper()), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # --- program attainment (KPI strip) ---
    section("Program attainment")
    kpis = [
        (f"{report.attainment_pct}%", "attainment"),
        (f"{report.evidence_complete_pct}%", "evidence complete"),
        (str(report.verification_overdue), "verification overdue"),
        (str(report.closed), "records closed"),
        (str(report.hftd_intersecting), "HFTD-intersecting"),
    ]
    w = 186 / len(kpis)
    y0 = pdf.get_y()
    for i, (val, _) in enumerate(kpis):
        pdf.set_xy(12 + i * w, y0)
        pdf.set_text_color(*DARK)
        pdf.set_font("Helvetica", "B", 15)
        pdf.cell(w, 8, val, align="C")
    for i, (_, lab) in enumerate(kpis):
        pdf.set_xy(12 + i * w, y0 + 8)
        pdf.set_text_color(*MUTE)
        pdf.set_font("Helvetica", "", 7)
        pdf.cell(w, 4, _ascii(lab), align="C")
    pdf.set_y(y0 + 14)
    pdf.ln(2)

    # --- risk governance ---
    section("Risk governance")
    pdf.set_text_color(*DARK)
    pdf.set_font("Helvetica", "", 9)
    d = report.risk_distribution
    pdf.cell(0, 5, _ascii(
        f"Distribution:  critical {d.get('critical',0)}   high {d.get('high',0)}   "
        f"elevated {d.get('elevated',0)}   low {d.get('low',0)}"),
        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 5, _ascii(f"Average risk score: {report.avg_risk_score}    "
                          f"Human-reviewed & signed: {report.reviewed_pct}%"),
             new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if report.unreviewed_high_or_critical:
        pdf.set_text_color(*RED)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, _ascii(f"{report.unreviewed_high_or_critical} high/critical span(s) awaiting a certified sign-off"),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    # --- span table (auto-paginates; heading row repeats on each page) ---
    section(f"Span detail ({len(report.spans)})")
    headings = ("Work order", "Circuit / Span", "Status", "Cov", "Evidence", "Risk", "Level", "Reviewed")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*DARK)
    with pdf.table(
        col_widths=(26, 36, 28, 14, 22, 14, 22, 24),  # sums to 186 = usable width
        text_align=("LEFT", "LEFT", "LEFT", "RIGHT", "LEFT", "RIGHT", "LEFT", "LEFT"),
        headings_style=FontFace(emphasis="BOLD", color=MUTE, fill_color=(240, 244, 241)),
        line_height=6, first_row_as_headings=True, width=186,
    ) as table:
        hr = table.row()
        for h in headings:
            hr.cell(h)
        for s in report.spans:
            cov = f"{s.coverage_pct}%" if s.coverage_pct is not None else "-"
            row = table.row()
            for v in (s.work_order_ref, f"{s.circuit} {s.span}", s.status.replace("_", " "),
                      cov, "complete" if s.evidence_complete else "incomplete",
                      str(s.risk_score), s.risk_level, "signed" if s.reviewed else "pending"):
                row.cell(_ascii(v))

    pdf.ln(3)
    pdf.set_text_color(*MUTE)
    pdf.set_font("Helvetica", "I", 7)
    pdf.multi_cell(0, 4, _ascii(report.note + "  -  CanopyOps Treatment Assurance."))

    return bytes(pdf.output())


@router.get("/reports/compliance.pdf")
def compliance_report_pdf(
    circuit: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    db: Session = Depends(get_db),
) -> Response:
    report = build_report(db, circuit, since, until)
    suffix = f"-{circuit}" if circuit else ""
    return Response(
        content=render_pdf(report, circuit, since),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="canopyops-compliance{suffix}.pdf"'},
    )
