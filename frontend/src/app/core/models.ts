/** Shared domain model — mirrors the FastAPI backend contracts (blueprint §08).
 *  Kept deliberately explicit so map, queue, and detail views share one truth. */

export type Role =
  | 'program_manager'
  | 'field_crew'
  | 'quality_reviewer'
  | 'compliance_reviewer';

export type TreatmentStatus =
  | 'draft'
  | 'scheduled'
  | 'in_progress'
  | 'applied'
  | 'awaiting_verification'
  | 'effective'
  | 'partially_effective'
  | 'ineffective'
  | 'inconclusive'
  | 'follow_up_planned'
  | 'closed';

export type MethodCategory =
  | 'manual'
  | 'mechanical'
  | 'herbicide'
  | 'biological'
  | 'cultural';

export type WorkOrderPriority = 'routine' | 'elevated' | 'hazard';

export type ConstraintCategory =
  | 'water_buffer'
  | 'habitat'
  | 'steep_slope'
  | 'no_work_zone'
  | 'access_restricted'
  | 'hftd';

export type ConstraintSeverity = 'advisory' | 'blocking';

export type EvidenceType =
  | 'photo_before'
  | 'photo_after'
  | 'clearance_measurement'
  | 'note'
  | 'form';

export type UploadStatus = 'pending' | 'uploading' | 'stored' | 'failed';

export type SyncStatus = 'accepted' | 'duplicate' | 'conflict' | 'rejected';

/** GeoJSON-lite (we only ever handle Point/LineString/Polygon here). */
export interface Geometry {
  type: 'Point' | 'LineString' | 'Polygon' | 'MultiPolygon';
  coordinates: any;
}

export interface AuthUser {
  id: string;
  email: string;
  displayName: string;
  role: Role;
}

export interface Corridor {
  id: string;
  circuitId: string;
  spanLabel: string;
  name: string;
  voltageKv: number;
  centerline: Geometry | null;
}

export interface EnvironmentalConstraint {
  id: string;
  name: string;
  category: ConstraintCategory;
  severity: ConstraintSeverity;
  geometry: Geometry | null;
}

/** Geofence proximity — escalating alert levels for a crew position. */
export type ProximityLevel = 'clear' | 'warning' | 'entered' | 'breach';

export interface ProximityZone {
  id: string;
  name: string;
  category: ConstraintCategory;
  severity: ConstraintSeverity;
  distanceM: number;
  inside: boolean;
  level: ProximityLevel;
  action: string;
}

export interface ProximityResult {
  lon: number;
  lat: number;
  warningMeters: number;
  overallLevel: ProximityLevel;
  nearestName: string | null;
  nearestDistanceM: number | null;
  zones: ProximityZone[];
  note: string;
}

export interface ZonesSnapshot {
  version: string;
  zones: EnvironmentalConstraint[];
}

/** Span Risk Intelligence — deterministic, explainable, human-reviewed. */
export type RiskLevel = 'low' | 'elevated' | 'high' | 'critical';

export interface RiskFactor {
  name: string;
  value: number;        // 0..1
  weight: number;       // points available
  contribution: number; // weight * value
  note: string;
}

export interface SpanRisk {
  planId: string;
  workOrderRef: string;
  circuit: string;
  span: string;
  score: number;        // 0..100
  level: RiskLevel;
  factors: RiskFactor[];
  recommendation: string;
  requiresReview: boolean;
  reviewed: boolean;
  reviewedBy: string | null;
  reviewedAt: string | null;
}

export interface RiskReview {
  id: string;
  planId: string;
  reviewerId: string | null;
  reviewerName: string | null;
  score: number;
  level: RiskLevel;
  decision: string;
  note: string | null;
  createdAt: string;
}

export interface RiskBoard {
  generatedAt: string;
  spans: SpanRisk[];
  note: string;
}

/** Synthetic digital elevation model rendered as an interactive 3D surface. */
export interface TerrainGrid {
  bbox: number[];          // [minLon, minLat, maxLon, maxLat]
  cols: number;
  rows: number;
  minElev: number;
  maxElev: number;
  elevations: number[][];  // rows x cols, metres
  note: string;
}

export interface TerrainProfilePoint {
  distanceM: number;
  elevationM: number;
  slopePct: number;
}

export interface TerrainProfile {
  points: TerrainProfilePoint[];
  lengthM: number;
  gainM: number;
  maxSlopePct: number;
  steepSections: number;
  steepThresholdPct: number;
  note: string;
}

/** Flattened queue/detail row: a plan joined with its work order + corridor,
 *  plus derived assurance signals the Command Center ranks on. */
export interface TreatmentRecord {
  planId: string;
  workOrderRef: string;
  corridor: { circuitId: string; spanLabel: string; name: string };
  priority: WorkOrderPriority;
  status: TreatmentStatus;
  methodCategory: MethodCategory;
  targetCondition: string;
  plannedGeometry: Geometry | null;
  actualGeometry: Geometry | null;
  requiredEvidence: EvidenceType[];
  /** Derived assurance signals (computed server-side). */
  evidenceComplete: boolean;
  evidenceScore: number;      // 0..1
  coverageRatio: number | null; // planned-vs-actual, 0..1
  verificationDueAt: string | null;
  verificationOverdue: boolean;
  constraintFlags: ConstraintCategory[];
  planRevision: number;
  updatedAt: string;
}

export interface ApiError {
  code: string;
  message: string;
  correlationId?: string;
  [key: string]: unknown;
}

// --- execution / offline outbox ---
export interface EvidenceInput {
  type: EvidenceType;
  capturedAt?: string;
  value?: Record<string, unknown>;
  simulateUploadFailure?: boolean;
}

export interface ExecutionPayload {
  planId: string;
  planRevision: number;
  actualGeometry: Geometry;
  performedAt?: string;
  notes?: string;
  constraintAcknowledged?: boolean;
  evidence: EvidenceInput[];
}

export interface EvidenceResult {
  id: string;
  type: EvidenceType;
  uploadStatus: UploadStatus;
}

export interface ExecutionResult {
  id: string;
  planId: string;
  planStatus: TreatmentStatus;
  coverageRatio: number | null;
  evidenceScore: number;
  evidenceComplete: boolean;
  evidence: EvidenceResult[];
  syncStatus: SyncStatus;
  serverRevision: number;
}

export interface ConflictDetail {
  code: string;
  message: string;
  planId: string;
  yourRevision: number;
  serverRevision: number;
}

export type VerificationConclusion =
  | 'effective'
  | 'partially_effective'
  | 'ineffective'
  | 'inconclusive';

export interface VerificationInput {
  conclusion: VerificationConclusion;
  condition?: string;
  regrowthObserved?: boolean;
  compatibleCover?: boolean;
  followupGeometry?: Geometry | null;
}

export interface ObservationOut {
  id: string;
  observedAt: string;
  conclusion: VerificationConclusion | null;
  condition: string | null;
  regrowthObserved: boolean;
  compatibleCover: boolean;
  followupGeometry: Geometry | null;
  reviewerId: string | null;
}

export interface VerificationResult {
  planId: string;
  status: TreatmentStatus;
  observation: ObservationOut;
}

export interface AuditOut {
  action: string;
  actorId: string | null;
  reason: string | null;
  createdAt: string;
}

export interface ProofPack {
  record: TreatmentRecord;
  plannedGeometry: Geometry | null;
  actualGeometry: Geometry | null;
  performedAt: string | null;
  evidence: EvidenceResult[];
  observations: ObservationOut[];
  auditTrail: AuditOut[];
}

// --- program overview dashboard ---
export interface KpiTile {
  key: string;
  label: string;
  value: string;
  unit: string;
  delta: number | null;
  deltaGood: boolean;
  spark: number[];
  tone: string;
  note: string | null;
}

export interface NamedSeries {
  label: string;
  tone: string;
  points: number[];
}

export interface InsightItem {
  title: string;
  tag: string;
}

export interface StatusCount {
  status: TreatmentStatus;
  count: number;
}

export interface ActivityItem {
  action: string;
  at: string;
  entityId: string;
}

export interface OverviewPayload {
  periodLabel: string;
  realPlanCount: number;
  generatedAt: string;
  statusDistribution: StatusCount[];
  recentActivity: ActivityItem[];
  tiles: KpiTile[];
  weeks: string[];
  plannedSpans: number[];
  completedSpans: number[];
  attainmentPct: number;
  cycleMix: NamedSeries[];
  cycleRegions: string[];
  mvcdPct: number;
  hftdTiers: NamedSeries[];
  hftdLabels: string[];
  saidiPoints: number[];
  auditPassPct: number;
  evidenceCompletePct: number;
  regrowthPoints: number[];
  refusalsPct: number;
  qualityBreakdown: NamedSeries[];
  costPerSpan: number[];
  productionRate: number[];
  insights: InsightItem[];
}

export interface ConstraintStatus {
  id: string;
  name: string;
  category: ConstraintCategory;
  severity: ConstraintSeverity;
  intersectingPlans: number;
}

export interface StewardshipPayload {
  tiles: KpiTile[];
  methodMix: NamedSeries[];
  compatibleCoverPct: number;
  ivmShiftNote: string;
  weeks: string[];
  pollinatorAcres: number[];
  constraints: ConstraintStatus[];
  realPlanCount: number;
  insights: InsightItem[];
}

export interface SystemHealth {
  uptime_s: number;
  total_requests: number;
  errors: number;
  error_rate: number;
  latency_ms: { p50: number; p95: number; p99: number };
  endpoints: { endpoint: string; count: number; errors: number; p50_ms: number; p95_ms: number }[];
}

export interface ConstraintBrief {
  id: string;
  name: string;
  category: ConstraintCategory;
  severity: ConstraintSeverity;
}

export interface GeoAnalyze {
  valid: boolean;
  areaAcres: number;
  intersectingConstraints: ConstraintBrief[];
  blocking: boolean;
}

export interface PlanInput {
  corridorId: string;
  priority: WorkOrderPriority;
  targetCondition: string;
  methodCategory: MethodCategory;
  requiredEvidence: EvidenceType[];
  verificationWindowDays: number;
  cycle: string;
  plannedGeometry: Geometry;
  dueInDays: number;
}

export interface RegionCell {
  id: string;
  name: string;
  circuit: string;
  geometry: Geometry;
  encroachments: number;
  mvcdPct: number;
  hftdTier: number;
  openWorkOrders: number;
  tone: string;
}

export interface EncroachmentMap {
  regions: RegionCell[];
  maxEncroachments: number;
  totalEncroachments: number;
  center: [number, number];
  note: string;
}

export type OutboxStatus = 'pending' | 'syncing' | 'synced' | 'failed' | 'conflict';

/** A field mutation captured locally, awaiting sync. The idempotencyKey makes
 *  replay safe; the payload is a self-contained record of what the crew did. */
export interface OutboxItem {
  id: string;
  idempotencyKey: string;
  label: string; // human summary e.g. "WO-2026-1001 execution"
  payload: ExecutionPayload;
  status: OutboxStatus;
  attempts: number;
  createdAt: string;
  lastError?: string;
  result?: ExecutionResult;
  conflict?: ConflictDetail;
}
