import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { ConnectivityService } from '../../core/connectivity.service';
import { centeredCoverageBox, normalizeToSvg } from '../../core/geometry';
import {
  EvidenceInput,
  EvidenceType,
  Geometry,
  TreatmentRecord,
} from '../../core/models';
import { CONSTRAINT_META, STATUS_META } from '../../core/status';
import { SyncService } from '../../core/sync.service';
import { ToastService } from '../../core/toast.service';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

interface EvidenceRow {
  type: EvidenceType;
  captured: boolean;
  canFail: boolean;
  simulateFail: boolean;
}

@Component({
  selector: 'app-field-execution',
  standalone: true,
  imports: [FormsModule, RouterLink, StatusBadgeComponent],
  templateUrl: './field-execution.component.html',
})
export class FieldExecutionComponent {
  private api = inject(ApiService);
  private sync = inject(SyncService);
  private auth = inject(AuthService);
  private toast = inject(ToastService);
  conn = inject(ConnectivityService);

  readonly STATUS_META = STATUS_META;
  readonly CONSTRAINT_META = CONSTRAINT_META;

  readonly plans = signal<TreatmentRecord[]>([]);
  readonly selectedId = signal<string | null>(null);
  readonly coverage = signal(100);
  readonly constraintAck = signal(false);
  readonly evidence = signal<EvidenceRow[]>([]);
  readonly savedMsg = signal<string | null>(null);
  readonly pending = this.sync.pending;

  readonly canRecord = computed(() =>
    this.auth.can('field_crew', 'program_manager'),
  );
  readonly selected = computed(
    () => this.plans().find((p) => p.planId === this.selectedId()) ?? null,
  );

  /** Actual treated polygon derived from the coverage control (scale² = area). */
  readonly actualGeometry = computed<Geometry | null>(() => {
    const plan = this.selected();
    if (!plan?.plannedGeometry || plan.plannedGeometry.type !== 'Polygon') return null;
    return centeredCoverageBox(plan.plannedGeometry, this.coverage() / 100);
  });

  /** Normalized SVG points (0..100) for the planned vs actual preview. */
  readonly preview = computed(() => {
    const plan = this.selected();
    if (!plan?.plannedGeometry) return null;
    return {
      planned: normalizeToSvg(plan.plannedGeometry, plan.plannedGeometry),
      actual: normalizeToSvg(plan.plannedGeometry, this.actualGeometry()),
    };
  });

  constructor() {
    this.api.listTreatments().subscribe((rows) => {
      const executable = rows.filter((r) =>
        ['draft', 'scheduled', 'in_progress', 'applied'].includes(r.status),
      );
      this.plans.set(executable);
    });
  }

  choose(planId: string): void {
    this.selectedId.set(planId);
    this.savedMsg.set(null);
    this.coverage.set(100);
    this.constraintAck.set(false);
    const plan = this.plans().find((p) => p.planId === planId);
    this.evidence.set(
      (plan?.requiredEvidence ?? []).map((type) => ({
        type,
        captured: true,
        canFail: type === 'photo_after',
        simulateFail: false,
      })),
    );
  }

  toggleCaptured(row: EvidenceRow): void {
    this.evidence.update((rows) =>
      rows.map((r) => (r.type === row.type ? { ...r, captured: !r.captured } : r)),
    );
  }

  toggleFail(row: EvidenceRow): void {
    this.evidence.update((rows) =>
      rows.map((r) => (r.type === row.type ? { ...r, simulateFail: !r.simulateFail } : r)),
    );
  }

  async save(): Promise<void> {
    const plan = this.selected();
    const geom = this.actualGeometry();
    if (!plan || !geom) return;
    const evidence: EvidenceInput[] = this.evidence()
      .filter((r) => r.captured)
      .map((r) => ({
        type: r.type,
        capturedAt: new Date().toISOString(),
        simulateUploadFailure: r.simulateFail,
      }));
    await this.sync.enqueue(`${plan.workOrderRef} execution`, {
      planId: plan.planId,
      planRevision: plan.planRevision,
      actualGeometry: geom,
      performedAt: new Date().toISOString(),
      constraintAcknowledged: this.constraintAck(),
      evidence,
    });
    const msg = this.conn.online()
      ? 'Saved and syncing — track it in the Sync Center.'
      : 'Saved locally. It will sync automatically when connectivity returns.';
    this.savedMsg.set(msg);
    this.toast.success(msg);
    this.selectedId.set(null);
  }
}
