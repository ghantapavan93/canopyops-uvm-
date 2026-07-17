"""Pydantic response/request contracts. camelCase on the wire to match the
Angular TypeScript models; snake_case in Python."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
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
    tenant_id: str
    tenant_name: str | None = None


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


# Cap import size to bound memory + one transaction (DoS guard).
MAX_IMPORT_FEATURES = 10_000


class GeoJSONImport(Schema):
    type: str = "FeatureCollection"
    features: list[dict] = Field(default_factory=list, max_length=MAX_IMPORT_FEATURES)


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


# --- compliance report (the exportable evidence artifact) ---
class ComplianceSpanRow(Schema):
    work_order_ref: str
    circuit: str
    span: str
    status: str
    coverage_pct: int | None
    evidence_complete: bool
    risk_score: float
    risk_level: str
    reviewed: bool


class ComplianceReport(Schema):
    generated_at: datetime
    # program
    total_plans: int
    attainment_pct: float          # share past "applied"
    evidence_complete_pct: float
    verification_overdue: int
    closed: int
    # regulatory
    hftd_intersecting: int
    # risk governance
    risk_distribution: dict[str, int]   # level -> count
    reviewed_pct: float
    unreviewed_high_or_critical: int
    avg_risk_score: float
    spans: list[ComplianceSpanRow]
    note: str = (
        "Independent concept · synthetic data. Illustrative compliance summary — "
        "not a regulatory filing."
    )


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
    # Where this number actually comes from. The dashboard mixes figures computed
    # from the live records with illustrative program-scale trends, and a
    # reviewer who cannot tell them apart has to distrust all of them — so every
    # tile states its provenance rather than leaving it to the footnote.
    #   live      — computed from the seeded records in this demo
    #   synthetic — an illustrative program-scale figure; nothing computes it
    #   blended   — a live value shown against a synthetic trend line
    source: Literal["live", "synthetic", "blended"] = "synthetic"


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


# --- reliability outcome (closed vs effective, in SAIDI/SAIFI/CAIDI/CMI) ---
class ReliabilityCircuit(Schema):
    circuit: str
    customers_served: int
    spans: int
    closed: int
    effective_closures: int
    ineffective_closures: int
    effectiveness_pct: int
    veg_share_pct: int
    saidi_before: float
    saidi_after: float
    saidi_delta: float
    saifi_before: float
    saifi_after: float
    caidi_before: float
    caidi_after: float
    cmi_before: int
    cmi_after: int
    classification: str  # effective | mixed | closed_not_effective | pending


class ReliabilityRollup(Schema):
    customers: int
    circuits: int
    closed_total: int
    effective_total: int
    ineffective_total: int
    saidi_before: float
    saidi_after: float
    saidi_delta: float
    saifi_before: float
    saifi_after: float
    cmi_before: int
    cmi_after: int
    closed_not_effective_circuits: int
    effective_circuits: int


class ReliabilityBoard(Schema):
    generated_at: datetime
    note: str
    rollup: ReliabilityRollup
    circuits: list[ReliabilityCircuit]


# --- vegetation intelligence: hot-spotting + cycle busters ---
class HotspotDrivers(Schema):
    reactive_pct: int
    effectiveness_gap_pct: int
    encroachment_pressure: int
    growth_pressure: int


class VegetationHotspot(Schema):
    corridor_id: str
    circuit: str
    span_label: str
    voltage_kv: int
    geometry: dict | None
    reactive_repeats: int
    planned_visits: int
    repeat_rate_pct: int
    hotspot_score: int
    tier: str  # hot | elevated | stable
    drivers: HotspotDrivers


class HotspotSummary(Schema):
    total: int
    hot: int
    elevated: int
    stable: int
    worst_circuit: str | None
    max_score: int


class HotspotBoard(Schema):
    generated_at: datetime
    note: str
    center: list[float]
    summary: HotspotSummary
    hotspots: list[VegetationHotspot]


class CycleBusterSpan(Schema):
    corridor_id: str
    circuit: str
    span_label: str
    voltage_kv: int
    species_common: str
    species_latin: str
    growth_ft_per_year: float
    is_cycle_buster: bool
    mvcd_headroom_ft: float
    days_to_conflict: int
    last_treated: datetime | None
    priority: str  # hazard | elevated | watch


class CycleBusterSummary(Schema):
    watchlist_total: int
    cycle_busters: int
    imminent: int
    fastest_species: str | None
    fastest_growth_ft: float


class CycleBusterBoard(Schema):
    generated_at: datetime
    note: str
    summary: CycleBusterSummary
    spans: list[CycleBusterSpan]


# --- work-plan QA audit (independent checks & balances) ---
class AuditCheck(Schema):
    key: str
    label: str
    passed: bool
    critical: bool
    detail: str


class AuditQueueItem(Schema):
    plan_id: str
    work_order_ref: str
    circuit: str
    span: str
    status: str
    checks: list[AuditCheck]
    score: float
    suggested_outcome: str
    sampled: bool
    audited: bool
    last_outcome: str | None
    last_auditor: str | None
    last_audited_at: datetime | None


class AuditSummary(Schema):
    total: int
    sampled: int
    audited: int
    passed: int
    failed: int
    conditional: int
    audit_coverage_pct: int


class AuditQueue(Schema):
    generated_at: datetime
    note: str
    summary: AuditSummary
    items: list[AuditQueueItem]


class AuditIn(Schema):
    outcome: str          # pass | conditional | fail
    note: str | None = None


class QualityAuditOut(Schema):
    id: str
    plan_id: str
    auditor_id: str | None
    auditor_name: str | None
    outcome: str
    score: float
    checks: list[AuditCheck]
    note: str | None
    created_at: datetime


# --- compliance evidence vault ---
class FrameworkStatus(Schema):
    code: str
    requirement: str
    satisfied: bool
    detail: str


class EvidenceRef(Schema):
    type: str
    stored: bool
    upload_status: str
    checksum: str | None
    storage_key: str | None
    captured_at: datetime | None


class VaultComponents(Schema):
    coverage: float | None
    coverage_ok: bool
    evidence_score: float
    evidence_complete: bool
    evidence: list[EvidenceRef]
    verified: bool
    constraint_intersects: bool
    constraint_ack: bool
    risk_reviewed: bool
    risk_reviewer: str | None
    qa_audited: bool
    qa_outcome: str | None
    qa_auditor: str | None


class Prescription(Schema):
    method: str
    target_condition: str
    required_evidence: list[str]
    revision: int


class PlanDossier(Schema):
    plan_id: str
    work_order_ref: str
    circuit: str
    span: str
    status: str
    prescription: Prescription
    components: VaultComponents
    frameworks: list[FrameworkStatus]
    completeness_pct: int
    satisfied: int
    requirements: int


class VaultSummary(Schema):
    plans: int
    fully_compliant: int
    avg_completeness_pct: int


class VaultIndex(Schema):
    generated_at: datetime
    note: str
    summary: VaultSummary
    plans: list[PlanDossier]


# --- background jobs (durable task queue) ---
class JobOut(Schema):
    id: str
    type: str
    status: str          # queued | running | succeeded | failed
    attempts: int
    max_attempts: int
    result: dict | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class GeoJSONImportJobIn(Schema):
    features: list[dict] = Field(max_length=MAX_IMPORT_FEATURES)


# --- evidence object-storage pipeline (presigned uploads) ---
class UploadUrlIn(Schema):
    content_type: str
    size_bytes: int


class UploadUrlOut(Schema):
    evidence_id: str
    upload_url: str
    storage_key: str
    method: str = "PUT"
    expires_seconds: int
    max_bytes: int


class FinalizeIn(Schema):
    checksum: str
    size_bytes: int | None = None


class EvidenceStatusOut(Schema):
    id: str
    type: e.EvidenceType
    upload_status: e.UploadStatus
    storage_key: str | None
    checksum: str | None
    download_url: str | None = None
    message: str | None = None
