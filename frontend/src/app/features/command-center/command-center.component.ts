import { DatePipe } from '@angular/common';
import { Component, HostListener, OnDestroy, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { forkJoin } from 'rxjs';

import { ApiService } from '../../core/api.service';
import {
  Corridor,
  EnvironmentalConstraint,
  ProofPack,
  TreatmentRecord,
  TreatmentStatus,
  WorkOrderPriority,
} from '../../core/models';
import {
  CONSTRAINT_META,
  PRIORITY_META,
  STATUS_META,
} from '../../core/status';
import { StatusBadgeComponent } from '../../shared/status-badge.component';
import { MapComponent } from './map.component';

const PRIORITIES: WorkOrderPriority[] = ['hazard', 'elevated', 'routine'];

/** Queue sort options. Each maps to a comparator over the visible records. */
export type SortKey = 'priority' | 'evidence' | 'due' | 'updated';
const SORTS: { key: SortKey; label: string }[] = [
  { key: 'priority', label: 'Priority' },
  { key: 'evidence', label: 'Evidence (worst first)' },
  { key: 'due', label: 'Due / overdue' },
  { key: 'updated', label: 'Recently updated' },
];
const PRIORITY_RANK: Record<WorkOrderPriority, number> = { hazard: 0, elevated: 1, routine: 2 };

@Component({
  selector: 'app-command-center',
  standalone: true,
  imports: [FormsModule, DatePipe, MapComponent, StatusBadgeComponent],
  templateUrl: './command-center.component.html',
})
export class CommandCenterComponent implements OnDestroy {
  private api = inject(ApiService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  readonly STATUS_META = STATUS_META;
  readonly PRIORITY_META = PRIORITY_META;
  readonly CONSTRAINT_META = CONSTRAINT_META;
  readonly priorities = PRIORITIES;
  readonly sorts = SORTS;

  readonly records = signal<TreatmentRecord[]>([]);
  readonly constraints = signal<EnvironmentalConstraint[]>([]);
  readonly corridors = signal<Corridor[]>([]);
  readonly loading = signal(true);
  readonly refreshing = signal(false);
  readonly error = signal<string | null>(null);

  // Filter + selection state (mirrors URL query params).
  readonly q = signal('');
  readonly activePriorities = signal<Set<WorkOrderPriority>>(new Set());
  readonly activeStatuses = signal<Set<TreatmentStatus>>(new Set());
  readonly attentionOnly = signal(false);
  readonly sortKey = signal<SortKey>('priority');
  readonly selectedId = signal<string | null>(null);
  readonly mobileTab = signal<'list' | 'map'>('list');

  readonly selected = computed(
    () => this.records().find((r) => r.planId === this.selectedId()) ?? null,
  );
  /** Full record history (Proof Pack) for the selected record — lazy-loaded. */
  readonly recordDetail = signal<ProofPack | null>(null);

  readonly visible = computed(() => {
    let rows = this.records();
    const statuses = this.activeStatuses();
    if (statuses.size) rows = rows.filter((r) => statuses.has(r.status));
    if (this.attentionOnly()) {
      rows = rows.filter((r) => r.verificationOverdue || !r.evidenceComplete);
    }
    return [...rows].sort(this.comparator(this.sortKey()));
  });

  /** Comparator for the active sort key. Overdue always floats within 'due'. */
  private comparator(key: SortKey): (a: TreatmentRecord, b: TreatmentRecord) => number {
    switch (key) {
      case 'evidence':
        return (a, b) => a.evidenceScore - b.evidenceScore;
      case 'due':
        return (a, b) => {
          if (a.verificationOverdue !== b.verificationOverdue) return a.verificationOverdue ? -1 : 1;
          const av = a.verificationDueAt ? Date.parse(a.verificationDueAt) : Infinity;
          const bv = b.verificationDueAt ? Date.parse(b.verificationDueAt) : Infinity;
          return av - bv;
        };
      case 'updated':
        return (a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt);
      case 'priority':
      default:
        return (a, b) => PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority];
    }
  }

  /** Distinct statuses present in the loaded records — drives the filter chips. */
  readonly statusOptions = computed(() => {
    const order = [
      'draft', 'scheduled', 'in_progress', 'applied', 'awaiting_verification',
      'effective', 'partially_effective', 'ineffective', 'inconclusive',
      'follow_up_planned', 'closed',
    ] as TreatmentStatus[];
    const present = new Set(this.records().map((r) => r.status));
    return order.filter((s) => present.has(s));
  });

  readonly attentionCount = computed(
    () =>
      this.records().filter((r) => r.verificationOverdue || !r.evidenceComplete).length,
  );

  // Backend-driven assurance summary — the story of the program at a glance.
  readonly summary = computed(() => {
    const rows = this.records();
    const n = rows.length || 1;
    return {
      total: rows.length,
      overdue: rows.filter((r) => r.verificationOverdue).length,
      incomplete: rows.filter((r) => !r.evidenceComplete).length,
      constrained: rows.filter((r) => r.constraintFlags.length > 0).length,
      avgEvidence: Math.round((rows.reduce((s, r) => s + r.evidenceScore, 0) / n) * 100),
    };
  });

  constructor() {
    // Reference data loads once.
    forkJoin({
      corridors: this.api.listCorridors(),
      constraints: this.api.listConstraints(),
    }).subscribe({
      next: ({ corridors, constraints }) => {
        this.corridors.set(corridors);
        this.constraints.set(constraints);
      },
      error: () => {},
    });

    // URL is the single source of truth for filters + selection. The subscription
    // is tied to this component's lifetime so it can't leak across navigations.
    this.route.queryParamMap.pipe(takeUntilDestroyed()).subscribe((pm) => {
      this.q.set(pm.get('q') ?? '');
      this.activePriorities.set(
        new Set((pm.get('priority')?.split(',').filter(Boolean) as WorkOrderPriority[]) ?? []),
      );
      this.activeStatuses.set(
        new Set((pm.get('status')?.split(',').filter(Boolean) as TreatmentStatus[]) ?? []),
      );
      this.attentionOnly.set(pm.get('attention') === '1');
      const sort = pm.get('sort') as SortKey | null;
      this.sortKey.set(sort && SORTS.some((s) => s.key === sort) ? sort : 'priority');
      const sel = pm.get('sel');
      this.selectedId.set(sel);
      this.reload();
      // Lazy-load the full record history (Proof Pack) for the selected record.
      this.recordDetail.set(null);
      if (sel) {
        this.api.getProof(sel).subscribe({
          next: (p) => this.recordDetail.set(p),
          error: () => this.recordDetail.set(null),
        });
      }
    });

    // 1s clock drives the "updated Ns ago" indicator without refetching.
    this.tick.set(Math.floor((Date.now() - this.start) / 1000));
    this.clockId = setInterval(
      () => this.tick.set(Math.floor((Date.now() - this.start) / 1000)),
      1000,
    );
    this.startPoll();
  }

  private reload(silent = false): void {
    if (silent) this.refreshing.set(true);
    else this.loading.set(true);
    this.error.set(null);
    this.api
      .listTreatments({
        q: this.q() || undefined,
        priority: [...this.activePriorities()],
      })
      .subscribe({
        next: (records) => {
          this.records.set(records);
          this.loading.set(false);
          this.refreshing.set(false);
          this.lastSync.set(this.tick());
        },
        error: (err) => {
          this.error.set(err?.error?.message ?? 'Could not load treatment records.');
          this.loading.set(false);
          this.refreshing.set(false);
        },
      });
  }

  // --- live refresh: the queue reflects real DB state, so it polls the API.
  // New/updated records appear without losing the current selection. ---
  readonly live = signal(true);
  readonly lastSync = signal(0);
  private readonly tick = signal(0);
  readonly agoSeconds = computed(() => Math.max(0, this.tick() - this.lastSync()));
  private clockId: ReturnType<typeof setInterval> | null = null;
  private pollId: ReturnType<typeof setInterval> | null = null;
  private readonly start = Date.now();

  refreshNow(): void {
    this.reload(true);
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
      if (this.live() && !document.hidden) this.reload(true);
    }, 12000);
  }

  ngOnDestroy(): void {
    if (this.clockId) clearInterval(this.clockId);
    if (this.pollId) clearInterval(this.pollId);
  }

  setSort(key: SortKey): void {
    this.patch({ sort: key === 'priority' ? null : key });
  }

  // --- keyboard navigation: ↑/↓ (or j/k) move through the queue, Enter opens
  // on mobile, Escape closes. Ignored while typing in the search box. ---
  @HostListener('document:keydown', ['$event'])
  onKey(ev: KeyboardEvent): void {
    const el = ev.target as HTMLElement | null;
    const typing = el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT');
    if (ev.key === 'Escape') {
      if (this.selectedId()) { this.selectRecord(null); ev.preventDefault(); }
      return;
    }
    if (typing) return;
    const rows = this.visible();
    if (!rows.length) return;
    if (ev.key === 'ArrowDown' || ev.key === 'j') { this.move(rows, 1); ev.preventDefault(); }
    else if (ev.key === 'ArrowUp' || ev.key === 'k') { this.move(rows, -1); ev.preventDefault(); }
    else if (ev.key === 'Enter' && this.selectedId()) { this.mobileTab.set('map'); ev.preventDefault(); }
  }

  private move(rows: TreatmentRecord[], delta: number): void {
    const cur = rows.findIndex((r) => r.planId === this.selectedId());
    const next = cur < 0 ? (delta > 0 ? 0 : rows.length - 1)
                         : Math.min(rows.length - 1, Math.max(0, cur + delta));
    const id = rows[next].planId;
    this.selectRecord(id, true);            // replaceUrl → no history spam
    queueMicrotask(() => document.getElementById(`q-${id}`)?.scrollIntoView({ block: 'nearest' }));
  }

  // --- URL-persisting mutations ---
  private patch(params: Record<string, string | null>, replaceUrl = false): void {
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: params,
      queryParamsHandling: 'merge',
      replaceUrl,
    });
  }

  onSearch(value: string): void {
    this.patch({ q: value || null });
  }

  togglePriority(p: WorkOrderPriority): void {
    const next = new Set(this.activePriorities());
    next.has(p) ? next.delete(p) : next.add(p);
    this.patch({ priority: next.size ? [...next].join(',') : null });
  }

  toggleStatus(s: TreatmentStatus): void {
    const next = new Set(this.activeStatuses());
    next.has(s) ? next.delete(s) : next.add(s);
    this.patch({ status: next.size ? [...next].join(',') : null });
  }

  toggleAttention(): void {
    this.patch({ attention: this.attentionOnly() ? null : '1' });
  }

  selectRecord(planId: string | null, replaceUrl = false): void {
    this.patch({ sel: planId }, replaceUrl);
    if (planId && !replaceUrl) this.mobileTab.set('map');
  }

  clearFilters(): void {
    this.router.navigate([], { relativeTo: this.route, queryParams: {} });
  }

  // Evidence meter width as a percentage string.
  pct(score: number): string {
    return `${Math.round(score * 100)}%`;
  }
}
