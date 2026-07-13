import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import {
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
  StewardshipPayload,
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

  getMetrics(): Observable<SystemHealth> {
    return this.http.get<SystemHealth>(`${this.base}/metrics`);
  }
}
