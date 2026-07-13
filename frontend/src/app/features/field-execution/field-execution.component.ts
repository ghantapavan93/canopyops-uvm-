import { Component, HostListener, OnDestroy, computed, inject, signal } from '@angular/core';
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
export class FieldExecutionComponent implements OnDestroy {
  private api = inject(ApiService);
  private sync = inject(SyncService);
  private auth = inject(AuthService);
  private toast = inject(ToastService);
  conn = inject(ConnectivityService);

  readonly STATUS_META = STATUS_META;
  readonly CONSTRAINT_META = CONSTRAINT_META;
  readonly coveragePresets = [100, 75, 50];

  readonly plans = signal<TreatmentRecord[]>([]);
  readonly selectedId = signal<string | null>(null);
  readonly coverage = signal(100);
  readonly constraintAck = signal(false);
  readonly evidence = signal<EvidenceRow[]>([]);
  readonly savedMsg = signal<string | null>(null);
  readonly refreshing = signal(false);
  readonly pending = this.sync.pending;

  readonly canRecord = computed(() =>
    this.auth.can('field_crew', 'program_manager'),
  );
  readonly selected = computed(
    () => this.plans().find((p) => p.planId === this.selectedId()) ?? null,
  );

  // --- Live evidence-completeness preview. Mirrors the server gate exactly:
  // only a captured, non-failed required item counts as "stored". So the crew
  // sees whether the record will submit COMPLETE (verifiable) or INCOMPLETE
  // (blocked) before they hit save. ---
  readonly evidenceRequired = computed(() => this.evidence().length);
  readonly evidenceStored = computed(
    () => this.evidence().filter((r) => r.captured && !r.simulateFail).length,
  );
  readonly evidenceScore = computed(() => {
    const req = this.evidenceRequired();
    return req === 0 ? 1 : this.evidenceStored() / req;
  });
  readonly evidenceComplete = computed(() => this.evidenceScore() >= 1);

  /** Live readiness — informational; partial submits are allowed by design
   *  (they stay incomplete and block verification until recovered). */
  readonly checklist = computed(() => {
    const plan = this.selected();
    const items = [
      { label: `Evidence captured (${this.evidenceStored()}/${this.evidenceRequired()})`, done: this.evidenceComplete() },
      { label: this.coverage() === 100 ? 'Full planned area covered' : `Partial coverage (${this.coverage()}%)`, done: this.coverage() === 100 },
    ];
    if (plan?.constraintFlags.length) {
      items.push({ label: 'Environmental constraints acknowledged', done: this.constraintAck() });
    }
    return items;
  });

  pct(score: number): string {
    return `${Math.round(score * 100)}%`;
  }

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
    this.loadPlans();
    this.tick.set(Math.floor((Date.now() - this.start) / 1000));
    this.clockId = setInterval(
      () => this.tick.set(Math.floor((Date.now() - this.start) / 1000)),
      1000,
    );
    this.startPoll();
  }

  private loadPlans(silent = false): void {
    if (silent) this.refreshing.set(true);
    this.api.listTreatments().subscribe({
      next: (rows) => {
        this.plans.set(
          rows.filter((r) => ['draft', 'scheduled', 'in_progress', 'applied'].includes(r.status)),
        );
        this.refreshing.set(false);
        this.lastSync.set(this.tick());
      },
      error: () => this.refreshing.set(false),
    });
  }

  // --- live refresh: newly-created / re-opened plans appear without losing the
  // capture in progress (selection is preserved; the open form is untouched). ---
  readonly live = signal(true);
  readonly lastSync = signal(0);
  private readonly tick = signal(0);
  readonly agoSeconds = computed(() => Math.max(0, this.tick() - this.lastSync()));
  private clockId: ReturnType<typeof setInterval> | null = null;
  private pollId: ReturnType<typeof setInterval> | null = null;
  private readonly start = Date.now();

  refreshNow(): void {
    this.loadPlans(true);
  }
  toggleLive(): void {
    const on = !this.live();
    this.live.set(on);
    if (on) this.startPoll();
    else if (this.pollId) { clearInterval(this.pollId); this.pollId = null; }
  }
  private startPoll(): void {
    if (this.pollId) clearInterval(this.pollId);
    this.pollId = setInterval(() => {
      // Never refetch mid-capture — it would be jarring while recording.
      if (this.live() && !document.hidden && !this.selectedId()) this.loadPlans(true);
    }, 12000);
  }
  ngOnDestroy(): void {
    if (this.clockId) clearInterval(this.clockId);
    if (this.pollId) clearInterval(this.pollId);
  }

  setCoverage(v: number): void {
    this.coverage.set(v);
  }

  // --- keyboard: in the picker, ↑/↓ (or j/k) move focus between plans (Enter
  // opens natively); in the capture form, Esc goes back and Ctrl/Cmd+Enter
  // records. Ignored while typing. ---
  @HostListener('document:keydown', ['$event'])
  onKey(ev: KeyboardEvent): void {
    const el = ev.target as HTMLElement | null;
    const typing = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT');
    if (this.selectedId()) {
      if (ev.key === 'Escape') { this.selectedId.set(null); ev.preventDefault(); }
      else if ((ev.ctrlKey || ev.metaKey) && ev.key === 'Enter' && this.canRecord()) { this.save(); ev.preventDefault(); }
      return;
    }
    if (typing) return;
    const rows = this.plans();
    if (!rows.length) return;
    if (ev.key === 'ArrowDown' || ev.key === 'j') { this.focusPlan(rows, 1); ev.preventDefault(); }
    else if (ev.key === 'ArrowUp' || ev.key === 'k') { this.focusPlan(rows, -1); ev.preventDefault(); }
  }

  private focusPlan(rows: TreatmentRecord[], delta: number): void {
    const active = document.activeElement?.id ?? '';
    const cur = rows.findIndex((r) => `plan-${r.planId}` === active);
    const next = cur < 0 ? (delta > 0 ? 0 : rows.length - 1)
                         : Math.min(rows.length - 1, Math.max(0, cur + delta));
    document.getElementById(`plan-${rows[next].planId}`)?.focus();
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
