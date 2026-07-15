import { DatePipe } from '@angular/common';
import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { ToastService } from '../../core/toast.service';
import { RiskBoard, RiskLevel, RiskReview, SpanRisk } from '../../core/models';

const FACTOR_META: Record<string, { label: string; cssVar: string }> = {
  clearance: { label: 'Encroachment', cssVar: '--c-primary' },
  growth: { label: 'Growth rate', cssVar: '--c-info' },
  wildfire: { label: 'Wildfire · HFTD', cssVar: '--c-danger' },
  slope: { label: 'Terrain slope', cssVar: '--c-warn' },
  outage: { label: 'Outage history', cssVar: '--c-neutral' },
};

const LEVELS: (RiskLevel | 'all')[] = ['all', 'critical', 'high', 'elevated', 'low'];

@Component({
  selector: 'app-risk',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './risk.component.html',
})
export class RiskComponent implements OnDestroy {
  private api = inject(ApiService);
  private auth = inject(AuthService);
  private toast = inject(ToastService);
  private router = inject(Router);

  readonly board = signal<RiskBoard | null>(null);
  readonly refreshing = signal(false);
  readonly levels = LEVELS;
  readonly levelFilter = signal<RiskLevel | 'all'>('all');
  private readonly signing = signal<Set<string>>(new Set());
  readonly canReview = computed(() => this.auth.can('quality_reviewer', 'compliance_reviewer'));

  readonly spans = computed(() => this.board()?.spans ?? []);
  readonly visible = computed(() => {
    const f = this.levelFilter();
    return f === 'all' ? this.spans() : this.spans().filter((s) => s.level === f);
  });
  readonly counts = computed(() => {
    const c: Record<string, number> = { critical: 0, high: 0, elevated: 0, low: 0 };
    for (const s of this.spans()) c[s.level]++;
    return c;
  });
  readonly reviewedCount = computed(() => this.spans().filter((s) => s.reviewed).length);

  // --- live refresh (consistent with the other consoles) ---
  readonly live = signal(true);
  readonly lastSync = signal(0);
  private readonly tick = signal(0);
  readonly agoSeconds = computed(() => Math.max(0, this.tick() - this.lastSync()));
  private clockId: ReturnType<typeof setInterval> | null = null;
  private pollId: ReturnType<typeof setInterval> | null = null;
  private readonly start = Date.now();

  constructor() {
    this.tick.set(0);
    this.clockId = setInterval(() => this.tick.set(Math.floor((Date.now() - this.start) / 1000)), 1000);
    this.load();
    this.startPoll();
  }
  ngOnDestroy(): void {
    if (this.clockId) clearInterval(this.clockId);
    if (this.pollId) clearInterval(this.pollId);
  }

  private load(silent = false): void {
    if (silent) this.refreshing.set(true);
    this.api.getRisk().subscribe({
      next: (b) => { this.board.set(b); this.refreshing.set(false); this.lastSync.set(this.tick()); },
      error: () => this.refreshing.set(false),
    });
  }
  refreshNow(): void { this.load(true); }
  toggleLive(): void {
    const on = !this.live();
    this.live.set(on);
    if (on) this.startPoll();
    else if (this.pollId) { clearInterval(this.pollId); this.pollId = null; }
  }
  private startPoll(): void {
    if (this.pollId) clearInterval(this.pollId);
    this.pollId = setInterval(() => { if (this.live() && !document.hidden) this.load(true); }, 15000);
  }

  setFilter(l: RiskLevel | 'all'): void { this.levelFilter.set(l); }

  factorLabel(name: string): string { return FACTOR_META[name]?.label ?? name; }
  factorColor(name: string): string { return `var(${FACTOR_META[name]?.cssVar ?? '--c-neutral'})`; }

  /** Persist a certified reviewer's sign-off (server records it + audits it). */
  signOff(s: SpanRisk): void { this.decide(s, 'acknowledged', `Signed off — recorded to the audit trail.`); }
  /** Revoke a prior sign-off — reopens the span; history is preserved. */
  revoke(s: SpanRisk): void { this.decide(s, 'revoked', 'Sign-off revoked — the span is reopened for review.'); }

  private decide(s: SpanRisk, decision: 'acknowledged' | 'revoked', ok: string): void {
    if (this.signing().has(s.planId)) return;
    this.signing.update((set) => new Set(set).add(s.planId));
    this.api.reviewSpan(s.planId, decision).subscribe({
      next: () => {
        this.toast.success(ok);
        this.clearSigning(s.planId);
        this.expandedHistory.update((set) => { const n = new Set(set); n.delete(s.planId); return n; });
        this.load(true);  // reflect the new persisted state
      },
      error: () => this.clearSigning(s.planId),  // the error interceptor toasts (e.g. 403)
    });
  }
  isSigning(s: SpanRisk): boolean { return this.signing().has(s.planId); }
  private clearSigning(id: string): void {
    this.signing.update((set) => { const n = new Set(set); n.delete(id); return n; });
  }

  // --- append-only review history (durable evidence trail) ---
  readonly expandedHistory = signal<Set<string>>(new Set());
  readonly history = signal<Record<string, RiskReview[]>>({});
  isHistoryOpen(s: SpanRisk): boolean { return this.expandedHistory().has(s.planId); }
  reviewsFor(s: SpanRisk): RiskReview[] { return this.history()[s.planId] ?? []; }
  toggleHistory(s: SpanRisk): void {
    const open = new Set(this.expandedHistory());
    if (open.has(s.planId)) { open.delete(s.planId); this.expandedHistory.set(open); return; }
    open.add(s.planId); this.expandedHistory.set(open);
    this.api.getReviews(s.planId).subscribe((revs) =>
      this.history.update((h) => ({ ...h, [s.planId]: revs })));
  }

  openInCommand(s: SpanRisk): void {
    this.router.navigate(['/console/command'], { queryParams: { q: s.circuit } });
  }

  levelTone(l: RiskLevel): 'danger' | 'warn' | 'info' | 'ok' {
    return l === 'critical' || l === 'high' ? 'danger' : l === 'elevated' ? 'warn' : 'ok';
  }
}
