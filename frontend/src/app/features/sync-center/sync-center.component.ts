import { Component, OnDestroy, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { ConnectivityService } from '../../core/connectivity.service';
import { OutboxItem, OutboxStatus } from '../../core/models';
import { TONE_CHIP, Tone } from '../../core/status';
import { SyncService } from '../../core/sync.service';

const OUTBOX_META: Record<OutboxStatus, { label: string; tone: Tone; glyph: string }> = {
  pending: { label: 'Queued locally', tone: 'info', glyph: '◔' },
  syncing: { label: 'Syncing…', tone: 'info', glyph: '⇅' },
  synced: { label: 'Synced', tone: 'ok', glyph: '●' },
  failed: { label: 'Failed — will retry', tone: 'warn', glyph: '▲' },
  conflict: { label: 'Conflict — needs you', tone: 'danger', glyph: '⚠' },
};

// Canonical order for the summary strip / composition bar.
const STATUS_ORDER: OutboxStatus[] = ['pending', 'syncing', 'synced', 'failed', 'conflict'];

type Filter = OutboxStatus | 'all';

@Component({
  selector: 'app-sync-center',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './sync-center.component.html',
})
export class SyncCenterComponent implements OnDestroy {
  sync = inject(SyncService);
  conn = inject(ConnectivityService);
  private api = inject(ApiService);

  readonly meta = OUTBOX_META;
  readonly statusOrder = STATUS_ORDER;
  readonly items = this.sync.items;

  // --- filter + inspector state ---
  readonly filter = signal<Filter>('all');
  private readonly expanded = signal<Set<string>>(new Set());

  /** Per-status counts, recomputed live as the outbox drains. */
  readonly counts = computed(() => {
    const c: Record<OutboxStatus, number> = { pending: 0, syncing: 0, synced: 0, failed: 0, conflict: 0 };
    for (const it of this.items()) c[it.status]++;
    return c;
  });

  /** Stacked composition bar segments (only statuses that exist). */
  readonly composition = computed(() => {
    const total = this.items().length || 1;
    const c = this.counts();
    return STATUS_ORDER.filter((s) => c[s] > 0).map((s) => ({
      status: s, tone: OUTBOX_META[s].tone, label: OUTBOX_META[s].label,
      count: c[s], pct: (c[s] / total) * 100,
    }));
  });

  /** The list, narrowed by the active filter chip. */
  readonly visible = computed(() => {
    const f = this.filter();
    return f === 'all' ? this.items() : this.items().filter((i) => i.status === f);
  });

  readonly failedCount = computed(() => this.counts().failed);
  readonly conflictCount = computed(() => this.counts().conflict);

  // --- live clock for relative "queued Ns ago" timestamps ---
  private readonly tick = signal(0);
  private clockId: ReturnType<typeof setInterval> | null = null;
  private readonly start = Date.now();

  constructor() {
    this.tick.set(0);
    this.clockId = setInterval(() => this.tick.set(Math.floor((Date.now() - this.start) / 1000)), 1000);
  }
  ngOnDestroy(): void {
    if (this.clockId) clearInterval(this.clockId);
  }

  setFilter(f: Filter): void {
    this.filter.set(this.filter() === f ? 'all' : f);
  }

  toggleExpand(id: string): void {
    this.expanded.update((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }
  isExpanded(id: string): boolean {
    return this.expanded().has(id);
  }

  chip(status: OutboxStatus): string {
    return TONE_CHIP[OUTBOX_META[status].tone];
  }

  pct(v: number): string {
    return `${Math.round(v * 100)}%`;
  }

  /** Short idempotency-key fingerprint for the row header. */
  keyShort(key: string): string {
    return key.slice(0, 8);
  }

  /** The exact request body that will be POSTed — shown in the inspector. */
  payloadJson(item: OutboxItem): string {
    return JSON.stringify(item.payload, null, 2);
  }

  /** Relative "3m ago", recomputed each clock tick. */
  ago(iso: string | undefined): string {
    this.tick();
    if (!iso) return '';
    const secs = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
    if (secs < 60) return `${secs}s ago`;
    const mins = Math.round(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    return `${Math.round(mins / 60)}h ago`;
  }

  // --- bulk actions over the whole outbox ---
  retryAllFailed(): void {
    for (const it of this.items()) if (it.status === 'failed') void this.sync.retry(it);
  }
  resolveAllConflicts(): void {
    for (const it of this.items()) if (it.status === 'conflict') void this.sync.resolveWithServer(it);
  }

  simulateEdit(item: OutboxItem): void {
    // Stand-in for a manager editing the plan on another device while this
    // execution sits in the outbox. Bumps server revision -> next sync conflicts.
    this.api.bumpPlanRevision(item.payload.planId).subscribe();
  }
}
