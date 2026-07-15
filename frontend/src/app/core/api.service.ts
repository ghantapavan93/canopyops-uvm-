import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import {
  ComplianceReport,
  Corridor,
  EnvironmentalConstraint,
  EncroachmentMap,
  GeoAnalyze,
  Geometry,
  ExecutionPayload,
  ExecutionResult,
  OverviewPayload,
  PlanInput,
  ProofPack,
  ProximityResult,
  RiskBoard,
  RiskReview,
  StewardshipPayload,
  TerrainGrid,
  TerrainProfile,
  ZonesSnapshot,
  SystemHealth,
  TreatmentRecord,
  VerificationInput,
  VerificationResult,
} from './models';

/** Thin typed gateway to the FastAPI backend. One place owns the base URL and
 *  query serialization so every feature speaks the same contract. */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = environment.apiBase;

  /** Command Center / queue rows, optionally filtered server-side. */
  listTreatments(filters: {
    status?: string[];
    priority?: string[];
    bbox?: [number, number, number, number];
    q?: string;
  } = {}): Observable<TreatmentRecord[]> {
    let params = new HttpParams();
    for (const s of filters.status ?? []) params = params.append('status', s);
    for (const p of filters.priority ?? []) params = params.append('priority', p);
    if (filters.q) params = params.set('q', filters.q);
    if (filters.bbox) params = params.set('bbox', filters.bbox.join(','));
    return this.http.get<TreatmentRecord[]>(`${this.base}/treatments`, { params });
  }

  getTreatment(planId: string): Observable<TreatmentRecord> {
    return this.http.get<TreatmentRecord>(`${this.base}/treatments/${planId}`);
  }

  listCorridors(): Observable<Corridor[]> {
    return this.http.get<Corridor[]>(`${this.base}/corridors`);
  }

  listConstraints(): Observable<EnvironmentalConstraint[]> {
    return this.http.get<EnvironmentalConstraint[]>(`${this.base}/constraints`);
  }

  /** Submit a field execution. The Idempotency-Key makes retries safe. */
  submitExecution(
    payload: ExecutionPayload,
    idempotencyKey: string,
  ): Observable<ExecutionResult> {
    return this.http.post<ExecutionResult>(`${this.base}/executions`, payload, {
      headers: { 'Idempotency-Key': idempotencyKey },
    });
  }

  retryEvidence(executionId: string, evidenceId: string): Observable<ExecutionResult> {
    return this.http.post<ExecutionResult>(
      `${this.base}/executions/${executionId}/evidence/${evidenceId}/retry`,
      {},
    );
  }

  /** Synthetic: simulate a manager editing the plan while a crew is offline. */
  bumpPlanRevision(planId: string): Observable<{ planId: string; serverRevision: number }> {
    return this.http.post<{ planId: string; serverRevision: number }>(
      `${this.base}/plans/${planId}/bump-revision`,
      {},
    );
  }

  verify(planId: string, input: VerificationInput): Observable<VerificationResult> {
    return this.http.post<VerificationResult>(`${this.base}/plans/${planId}/verify`, input);
  }

  planFollowup(planId: string): Observable<VerificationResult> {
    return this.http.post<VerificationResult>(`${this.base}/plans/${planId}/plan-followup`, {});
  }

  closePlan(planId: string): Observable<VerificationResult> {
    return this.http.post<VerificationResult>(`${this.base}/plans/${planId}/close`, {});
  }

  getProof(planId: string): Observable<ProofPack> {
    return this.http.get<ProofPack>(`${this.base}/plans/${planId}/proof`);
  }

  getOverview(period = 'ytd'): Observable<OverviewPayload> {
    return this.http.get<OverviewPayload>(`${this.base}/overview`, {
      params: { period },
    });
  }

  getEncroachments(): Observable<EncroachmentMap> {
    return this.http.get<EncroachmentMap>(`${this.base}/encroachments`);
  }

  createPlan(input: PlanInput): Observable<TreatmentRecord> {
    return this.http.post<TreatmentRecord>(`${this.base}/plans`, input);
  }

  getStewardship(): Observable<StewardshipPayload> {
    return this.http.get<StewardshipPayload>(`${this.base}/stewardship`);
  }

  analyzeGeometry(geometry: Geometry): Observable<GeoAnalyze> {
    return this.http.post<GeoAnalyze>(`${this.base}/geo/analyze`, { geometry });
  }

  /** Geofence check for a crew position — server-computed distances/levels. */
  proximity(lon: number, lat: number, warningMeters: number): Observable<ProximityResult> {
    return this.http.post<ProximityResult>(`${this.base}/geo/proximity`, {
      lon, lat, warningMeters,
    });
  }

  /** Versioned protected-zone snapshot cached on-device for offline geofencing. */
  getZones(): Observable<ZonesSnapshot> {
    return this.http.get<ZonesSnapshot>(`${this.base}/geo/zones`);
  }

  /** Synthetic DEM grid for the 3D terrain surface. */
  getTerrain(cols = 56, rows = 36): Observable<TerrainGrid> {
    return this.http.get<TerrainGrid>(`${this.base}/geo/terrain?cols=${cols}&rows=${rows}`);
  }

  /** Deterministic, explainable span risk scores (decision-support). */
  getRisk(): Observable<RiskBoard> {
    return this.http.get<RiskBoard>(`${this.base}/risk/spans`);
  }

  /** A certified reviewer signs off on (or revokes) a span's risk — persisted + audited. */
  reviewSpan(planId: string, decision: 'acknowledged' | 'revoked' = 'acknowledged', note?: string): Observable<RiskReview> {
    return this.http.post<RiskReview>(`${this.base}/risk/spans/${planId}/review`, {
      decision, note: note ?? null,
    });
  }

  /** The full append-only review history for a span (newest first). */
  getReviews(planId: string): Observable<RiskReview[]> {
    return this.http.get<RiskReview[]>(`${this.base}/risk/spans/${planId}/reviews`);
  }

  /** Exportable compliance rollup (print-ready), optionally scoped by circuit + date. */
  getComplianceReport(circuit?: string, since?: string): Observable<ComplianceReport> {
    const p: string[] = [];
    if (circuit) p.push(`circuit=${encodeURIComponent(circuit)}`);
    if (since) p.push(`since=${encodeURIComponent(since)}`);
    return this.http.get<ComplianceReport>(`${this.base}/reports/compliance${p.length ? '?' + p.join('&') : ''}`);
  }

  /** Elevation + slope profile along a corridor centerline. */
  terrainProfile(geometry: Geometry, samples = 48): Observable<TerrainProfile> {
    return this.http.post<TerrainProfile>(`${this.base}/geo/terrain/profile`, { geometry, samples });
  }

  getMetrics(): Observable<SystemHealth> {
    return this.http.get<SystemHealth>(`${this.base}/metrics`);
  }
}
