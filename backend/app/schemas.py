"""Pydantic response/request contracts. camelCase on the wire to match the
Angular TypeScript models; snake_case in Python."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.models import enums as e


class Schema(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# --- auth ---
class AuthUser(Schema):
    id: str
    email: str
    display_name: str
    role: e.Role


class TokenResponse(Schema):
    access_token: str
    token_type: str = "bearer"
    user: AuthUser


# --- geo-bearing reference data ---
class CorridorOut(Schema):
    id: str
    circuit_id: str
    span_label: str
    name: str
    voltage_kv: int
    centerline: dict | None


class ConstraintOut(Schema):
    id: str
    name: str
    category: e.ConstraintCategory
    severity: e.ConstraintSeverity
    geometry: dict | None


# --- the core queue/detail record ---
class CorridorRef(Schema):
    circuit_id: str
    span_label: str
    name: str


class TreatmentRecord(Schema):
    plan_id: str
    work_order_ref: str
    corridor: CorridorRef
    priority: e.WorkOrderPriority
    status: e.TreatmentStatus
    method_category: e.MethodCategory
    target_condition: str
    planned_geometry: dict | None
    actual_geometry: dict | None
    required_evidence: list[e.EvidenceType]
    evidence_complete: bool
    evidence_score: float
    coverage_ratio: float | None
    verification_due_at: datetime | None
    verification_overdue: bool
    constraint_flags: list[e.ConstraintCategory]
    plan_revision: int = 1
    updated_at: datetime


# --- execution / offline sync ---
class EvidenceIn(Schema):
    type: e.EvidenceType
    captured_at: datetime | None = None
    geolocation: dict | None = None
    value: dict = {}
    # Synthetic switch: crews can flag a photo that "fails" to upload, to
    # demonstrate partial-failure recovery. Never present in real capture.
    simulate_upload_failure: bool = False


class ExecutionIn(Schema):
    plan_id: str
    # The plan revision the crew's device last saw. If the server has moved on,
    # the sync is a conflict requiring human resolution — never last-write-wins.
    plan_revision: int
    actual_geometry: dict
    performed_at: datetime | None = None
    notes: str | None = None
    constraint_acknowledged: bool = False
    evidence: list[EvidenceIn] = []


class EvidenceResult(Schema):
    id: str
    type: e.EvidenceType
    upload_status: e.UploadStatus


class ExecutionResult(Schema):
    id: str
    plan_id: str
    plan_status: e.TreatmentStatus
    coverage_ratio: float | None
    evidence_score: float
    evidence_complete: bool
    evidence: list[EvidenceResult]
    sync_status: e.SyncStatus
    server_revision: int


class ConflictDetail(Schema):
    """Returned on 409 — enough for the Sync Center to explain the situation."""
    code: str = "revision_conflict"
    message: str
    plan_id: str
    your_revision: int
    server_revision: int


# --- verification / close ---
class VerificationIn(Schema):
    conclusion: e.VerificationConclusion
    condition: str | None = None
    regrowth_observed: bool = False
    compatible_cover: bool = False
    # Reviewer draws ONLY the area needing another pass (not a blind repeat).
    followup_geometry: dict | None = None


class ObservationOut(Schema):
    id: str
    observed_at: datetime
    conclusion: e.VerificationConclusion | None
    condition: str | None
    regrowth_observed: bool
    compatible_cover: bool
    followup_geometry: dict | None
    reviewer_id: str | None


class VerificationResult(Schema):
    plan_id: str
    status: e.TreatmentStatus
    observation: ObservationOut


class AuditOut(Schema):
    action: str
    actor_id: str | None
    reason: str | None
    created_at: datetime


class GeoJSONImport(Schema):
    type: str = "FeatureCollection"
    features: list[dict] = []


class ImportResult(Schema):
    imported: int
    skipped: int
    corridor_ids: list[str]
    message: str


class ConstraintBrief(Schema):
    id: str
    name: str
    category: e.ConstraintCategory
    severity: e.ConstraintSeverity


class GeoAnalyzeIn(Schema):
    geometry: dict


class GeoAnalyzeOut(Schema):
    valid: bool
    area_acres: float
    intersecting_constraints: list[ConstraintBrief]
    blocking: bool


# --- geofence / proximity alerts ---
class ProximityIn(Schema):
    lon: float
    lat: float
    # Detection radius: crews are warned this far from a protected boundary.
    warning_meters: float = 60.0


class ProximityZone(Schema):
    id: str
    name: str
    category: e.ConstraintCategory
    severity: e.ConstraintSeverity
    distance_m: float
    inside: bool
    level: str  # clear | warning | entered | breach
    action: str


class ProximityOut(Schema):
    lon: float
    lat: float
    warning_meters: float
    overall_level: str
    nearest_name: str | None
    nearest_distance_m: float | None
    zones: list[ProximityZone]
    note: str = "Synthetic constraints — illustrative only. Distances via PostGIS geography."


class ZonesSnapshot(Schema):
    """A cacheable snapshot of protected zones — the payload a field device
    stores so geofence alerts still work with no connectivity."""
    version: str
    zones: list[ConstraintOut]


# --- span risk intelligence (deterministic, explainable, human-reviewed) ---
class RiskFactor(Schema):
    name: str
    value: float        # 0..1 normalized signal
    weight: int         # points this factor can contribute
    contribution: float  # weight * value (points added to the composite)
    note: str


class SpanRisk(Schema):
    plan_id: str
    work_order_ref: str
    circuit: str
    span: str
    score: float        # 0..100 composite
    level: str          # low | elevated | high | critical
    factors: list[RiskFactor]
    recommendation: str
    requires_review: bool = True  # a machine never authorizes work
    # Populated once a certified human has signed off (durable evidence).
    reviewed: bool = False
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


class RiskReviewIn(Schema):
    decision: str = "acknowledged"
    note: str | None = None


class RiskReviewOut(Schema):
    id: str
    plan_id: str
    reviewer_id: str | None
    reviewer_name: str | None
    score: float
    level: str
    decision: str
    note: str | None
    created_at: datetime


class RiskBoard(Schema):
    generated_at: datetime
    spans: list[SpanRisk]  # ranked, highest risk first
    note: str = (
        "Deterministic, transparent risk scores — decision-support only. "
        "Every recommendation requires a certified human reviewer. Synthetic data."
    )


# --- 3D terrain awareness ---
class TerrainGrid(Schema):
    """A synthetic digital elevation model (DEM) over the sandbox, sampled on a
    regular grid. Rendered as an interactive 3D surface on the front end."""
    bbox: list[float]              # [minLon, minLat, maxLon, maxLat]
    cols: int
    rows: int
    min_elev: float
    max_elev: float
    elevations: list[list[float]]  # rows x cols, metres
    note: str = "Synthetic elevation model — illustrative only. Not survey data."


class TerrainProfileIn(Schema):
    geometry: dict                 # a GeoJSON LineString (e.g. a corridor centerline)
    samples: int = 48


class TerrainProfilePoint(Schema):
    distance_m: float
    elevation_m: float
    slope_pct: float


class TerrainProfileOut(Schema):
    points: list[TerrainProfilePoint]
    length_m: float
    gain_m: float
    max_slope_pct: float
    steep_sections: int
    steep_threshold_pct: float = 30.0
    note: str = "Synthetic elevation model — illustrative only. Not survey data."


class PlanCreate(Schema):
    corridor_id: str
    priority: e.WorkOrderPriority = e.WorkOrderPriority.ROUTINE
    target_condition: str
    method_category: e.MethodCategory
    required_evidence: list[e.EvidenceType] = []
    verification_window_days: int = 30
    cycle: str = "mid_cycle"
    planned_geometry: dict
    due_in_days: int = 14


class RegionCell(Schema):
    id: str
    name: str
    circuit: str
    geometry: dict
    encroachments: int
    mvcd_pct: float
    hftd_tier: int
    open_work_orders: int
    tone: str


class EncroachmentMap(Schema):
    regions: list[RegionCell]
    max_encroachments: int
    total_encroachments: int
    center: list[float]
    note: str = "Synthetic service districts — illustrative only."


class KpiTile(Schema):
    key: str
    label: str
    value: str
    unit: str = ""
    delta: float | None = None
    delta_good: bool = True  # is an increase good?
    spark: list[float] = []
    tone: str = "neutral"
    note: str | None = None


class NamedSeries(Schema):
    label: str
    tone: str = "primary"
    points: list[float]


class InsightItem(Schema):
    title: str
    tag: str


class StatusCount(Schema):
    status: e.TreatmentStatus
    count: int


class ActivityItem(Schema):
    action: str
    at: datetime
    entity_id: str


class OverviewPayload(Schema):
    period_label: str
    real_plan_count: int
    generated_at: datetime
    status_distribution: list[StatusCount]
    recent_activity: list[ActivityItem]
    tiles: list[KpiTile]
    # Program Attainment & Production
    weeks: list[str]
    planned_spans: list[float]
    completed_spans: list[float]
    attainment_pct: float
    cycle_mix: list[NamedSeries]  # cycle / mid-cycle / hazard counts by region
    cycle_regions: list[str]
    # Compliance & Wildfire Risk
    mvcd_pct: float
    hftd_tiers: list[NamedSeries]  # completion by HFTD tier
    hftd_labels: list[str]
    saidi_points: list[float]
    # Field Quality & Assurance
    audit_pass_pct: float
    evidence_complete_pct: float
    regrowth_points: list[float]
    refusals_pct: float
    quality_breakdown: list[NamedSeries]  # donut: complete/partial/blocked
    # Cost & Efficiency
    cost_per_span: list[float]
    production_rate: list[float]
    insights: list[InsightItem]


class ProofPack(Schema):
    """A synthetic, reviewable package: plan → execution → evidence →
    verification → audit, all connected. Only a fully closed-loop record has
    every section populated."""
    record: TreatmentRecord
    planned_geometry: dict | None
    actual_geometry: dict | None
    performed_at: datetime | None
    evidence: list[EvidenceResult]
    observations: list[ObservationOut]
    audit_trail: list[AuditOut]


# --- stewardship & compliance (defined after KpiTile/NamedSeries/InsightItem) ---
class ConstraintStatus(Schema):
    id: str
    name: str
    category: e.ConstraintCategory
    severity: e.ConstraintSeverity
    intersecting_plans: int


class StewardshipPayload(Schema):
    tiles: list[KpiTile]
    method_mix: list[NamedSeries]
    compatible_cover_pct: float
    ivm_shift_note: str
    weeks: list[str]
    pollinator_acres: list[float]
    constraints: list[ConstraintStatus]
    real_plan_count: int
    insights: list[InsightItem]
