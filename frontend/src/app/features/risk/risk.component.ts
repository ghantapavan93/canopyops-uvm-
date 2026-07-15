import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { RiskBoard, RiskLevel, SpanRisk } from '../../core/models';

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
  templateUrl: './risk.component.html',
})
export class RiskComponent implements OnDestroy {
  private api = inject(ApiService);
  private router = inject(Router);

  readonly board = signal<RiskBoard | null>(null);
  readonly refreshing = signal(false);
  readonly levels = LEVELS;
  readonly levelFilter = signal<RiskLevel | 'all'>('all');
  readonly reviewed = signal<Set<string>>(new Set());

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
  readonly reviewedCount = computed(() => this.reviewed().size);

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

  signOff(s: SpanRisk): void {
    this.reviewed.update((set) => new Set(set).add(s.planId));
  }
  isReviewed(s: SpanRisk): boolean { return this.reviewed().has(s.planId); }

  openInCommand(s: SpanRisk): void {
    this.router.navigate(['/console/command'], { queryParams: { q: s.circuit } });
  }

  levelTone(l: RiskLevel): 'danger' | 'warn' | 'info' | 'ok' {
    return l === 'critical' || l === 'high' ? 'danger' : l === 'elevated' ? 'warn' : 'ok';
  }
}
