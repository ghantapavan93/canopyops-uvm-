import { DatePipe } from '@angular/common';
import { Component, HostListener, OnDestroy, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { PolygonDrawMapComponent } from '../../shared/charts/polygon-draw-map.component';
import { RoleGateComponent } from '../../shared/role-gate.component';
import {
  Geometry,
  ProofPack,
  TreatmentRecord,
  VerificationConclusion,
} from '../../core/models';
import { STATUS_META } from '../../core/status';
import { ToastService } from '../../core/toast.service';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

const CONCLUSIONS: { value: VerificationConclusion; label: string }[] = [
  { value: 'effective', label: 'Effective' },
  { value: 'partially_effective', label: 'Partially effective' },
  { value: 'ineffective', label: 'Ineffective' },
  { value: 'inconclusive', label: 'Inconclusive' },
];

type QueueFilter = 'all' | 'awaiting' | 'overdue' | 'concluded';

@Component({
  selector: 'app-verification',
  standalone: true,
  imports: [FormsModule, RouterLink, DatePipe, StatusBadgeComponent, PolygonDrawMapComponent, RoleGateComponent],
  templateUrl: './verification.component.html',
})
export class VerificationComponent implements OnDestroy {
  private api = inject(ApiService);
  private auth = inject(AuthService);
  private toast = inject(ToastService);

  readonly STATUS_META = STATUS_META;
  readonly conclusions = CONCLUSIONS;

  readonly records = signal<TreatmentRecord[]>([]);
  readonly selectedId = signal<string | null>(null);
  readonly busy = signal(false);
  readonly refreshing = signal(false);
  readonly error = signal<string | null>(null);
  readonly proof = signal<ProofPack | null>(null);

  // --- queue filter (verification debt is the point: overdue floats up) ---
  readonly filter = signal<QueueFilter>('all');
  readonly filters: { key: QueueFilter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'awaiting', label: '◇ Awaiting' },
    { key: 'overdue', label: '⏳ Overdue' },
    { key: 'concluded', label: '● Concluded' },
  ];
  private isAwaiting = (r: TreatmentRecord) => r.status === 'awaiting_verification';
  private isConcluded = (r: TreatmentRecord) => !this.isAwaiting(r);

  readonly counts = computed(() => {
    const rows = this.records();
    return {
      all: rows.length,
      awaiting: rows.filter(this.isAwaiting).length,
      overdue: rows.filter((r) => r.verificationOverdue).length,
      concluded: rows.filter(this.isConcluded).length,
    };
  });

  /** Queue narrowed by the active filter, overdue-first then by coverage. */
  readonly visible = computed(() => {
    const f = this.filter();
    let rows = this.records();
    if (f === 'awaiting') rows = rows.filter(this.isAwaiting);
    else if (f === 'overdue') rows = rows.filter((r) => r.verificationOverdue);
    else if (f === 'concluded') rows = rows.filter(this.isConcluded);
    return [...rows].sort((a, b) => {
      if (a.verificationOverdue !== b.verificationOverdue) return a.verificationOverdue ? -1 : 1;
      return (a.coverageRatio ?? 1) - (b.coverageRatio ?? 1);
    });
  });

  // form state
  readonly conclusion = signal<VerificationConclusion>('partially_effective');
  readonly condition = signal('');
  readonly regrowth = signal(false);
  readonly compatible = signal(false);
  /** Reviewer's free-drawn rework polygon (from the map). */
  readonly drawnFollowup = signal<Geometry | null>(null);

  readonly canReview = computed(() =>
    this.auth.can('quality_reviewer', 'compliance_reviewer'),
  );
  readonly selected = computed(
    () => this.records().find((r) => r.planId === this.selectedId()) ?? null,
  );
  readonly needsFollowup = computed(() => this.conclusion() !== 'effective');

  /** Targeted follow-up = only the area the reviewer drew (never a blind repeat). */
  readonly followupGeometry = computed<Geometry | null>(() =>
    this.needsFollowup() ? this.drawnFollowup() : null,
  );

  /** Live "what will be recorded" summary — updates as the reviewer decides. */
  readonly outcomeSummary = computed(() => {
    const c = this.conclusion();
    const label = CONCLUSIONS.find((x) => x.value === c)?.label ?? c;
    return {
      conclusionLabel: label,
      resultingStatus: c,
      regrowth: this.regrowth(),
      compatible: this.compatible(),
      hasCondition: this.condition().trim().length > 0,
      followupAttached: this.followupGeometry() !== null,
      nextStep: c === 'effective'
        ? 'Ready to close — no follow-up needed.'
        : this.followupGeometry()
          ? 'Targeted follow-up geometry attached; plan follow-up, then close.'
          : 'Plan a follow-up (optionally draw the rework area), then close.',
    };
  });

  onFollowupGeometry(g: Geometry | null): void {
    this.drawnFollowup.set(g);
  }

  constructor() {
    this.load();
    this.tick.set(0);
    this.clockId = setInterval(() => this.tick.set(Math.floor((Date.now() - this.start) / 1000)), 1000);
    this.startPoll();
  }

  private load(silent = false): void {
    if (silent) this.refreshing.set(true);
    this.api.listTreatments({
      status: ['awaiting_verification', 'effective', 'partially_effective', 'ineffective', 'inconclusive', 'follow_up_planned'],
    }).subscribe({
      next: ({ items }) => {
        this.records.set(items);
        this.refreshing.set(false);
        this.lastSync.set(this.tick());
      },
      error: () => this.refreshing.set(false),
    });
  }

  // --- live refresh: verification debt appears/clears without disrupting an
  // in-progress review (poll pauses while a record is open). ---
  readonly live = signal(true);
  readonly lastSync = signal(0);
  private readonly tick = signal(0);
  readonly agoSeconds = computed(() => Math.max(0, this.tick() - this.lastSync()));
  private clockId: ReturnType<typeof setInterval> | null = null;
  private pollId: ReturnType<typeof setInterval> | null = null;
  private readonly start = Date.now();

  refreshNow(): void {
    this.load(true);
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
      if (this.live() && !document.hidden && !this.selectedId() && !this.proof()) this.load(true);
    }, 12000);
  }
  ngOnDestroy(): void {
    if (this.clockId) clearInterval(this.clockId);
    if (this.pollId) clearInterval(this.pollId);
  }

  setFilter(f: QueueFilter): void {
    this.filter.set(this.filter() === f ? 'all' : f);
  }

  // --- keyboard: queue ↑/↓ (j/k) move focus (Enter opens natively); in a
  // record, Esc goes back and Ctrl/Cmd+Enter records or closes. ---
  @HostListener('document:keydown', ['$event'])
  onKey(ev: KeyboardEvent): void {
    const el = ev.target as HTMLElement | null;
    const typing = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT');
    if (this.proof()) {
      if (ev.key === 'Escape') { this.proof.set(null); this.selectedId.set(null); ev.preventDefault(); }
      return;
    }
    if (this.selectedId()) {
      const plan = this.selected();
      if (ev.key === 'Escape') { this.selectedId.set(null); ev.preventDefault(); return; }
      if ((ev.ctrlKey || ev.metaKey) && ev.key === 'Enter' && plan && !this.busy() && this.canReview()) {
        if (plan.status === 'awaiting_verification' && plan.evidenceComplete) this.submitVerify();
        else if (plan.status !== 'awaiting_verification') this.close();
        ev.preventDefault();
      }
      return;
    }
    if (typing) return;
    const rows = this.visible();
    if (!rows.length) return;
    if (ev.key === 'ArrowDown' || ev.key === 'j') { this.focusRow(rows, 1); ev.preventDefault(); }
    else if (ev.key === 'ArrowUp' || ev.key === 'k') { this.focusRow(rows, -1); ev.preventDefault(); }
  }

  private focusRow(rows: TreatmentRecord[], delta: number): void {
    const active = document.activeElement?.id ?? '';
    const cur = rows.findIndex((r) => `v-${r.planId}` === active);
    const next = cur < 0 ? (delta > 0 ? 0 : rows.length - 1)
                         : Math.min(rows.length - 1, Math.max(0, cur + delta));
    document.getElementById(`v-${rows[next].planId}`)?.focus();
  }

  choose(id: string): void {
    this.selectedId.set(id);
    this.error.set(null);
    this.proof.set(null);
    this.conclusion.set('partially_effective');
    this.condition.set('');
    this.regrowth.set(false);
    this.compatible.set(false);
    this.drawnFollowup.set(null);
  }

  submitVerify(): void {
    const plan = this.selected();
    if (!plan) return;
    this.busy.set(true);
    this.error.set(null);
    this.api
      .verify(plan.planId, {
        conclusion: this.conclusion(),
        condition: this.condition() || undefined,
        regrowthObserved: this.regrowth(),
        compatibleCover: this.compatible(),
        followupGeometry: this.followupGeometry(),
      })
      .subscribe({
        next: () => { this.busy.set(false); this.load(); this.toast.success('Outcome recorded.'); },
        error: (e) => {
          this.busy.set(false);
          const msg = e?.error?.detail?.message ?? e?.error?.message ?? 'Verification failed.';
          this.error.set(msg);
          this.toast.error(msg);
        },
      });
  }

  planFollowup(): void {
    const plan = this.selected();
    if (!plan) return;
    this.busy.set(true);
    this.api.planFollowup(plan.planId).subscribe({
      next: () => { this.busy.set(false); this.load(); },
      error: (e) => { this.busy.set(false); this.error.set(e?.error?.detail?.message ?? 'Failed.'); },
    });
  }

  close(): void {
    const plan = this.selected();
    if (!plan) return;
    this.busy.set(true);
    this.api.closePlan(plan.planId).subscribe({
      next: () => {
        this.busy.set(false);
        this.api.getProof(plan.planId).subscribe((p) => this.proof.set(p));
        this.load();
        this.toast.success('Record closed — Proof Pack assembled.');
      },
      error: (e) => {
        this.busy.set(false);
        const msg = e?.error?.detail?.message ?? 'Failed to close.';
        this.error.set(msg);
        this.toast.error(msg);
      },
    });
  }

  pct(v: number | null): string {
    return v === null ? '—' : `${Math.round(v * 100)}%`;
  }
}
