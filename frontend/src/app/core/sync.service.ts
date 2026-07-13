import { HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, effect, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from './api.service';
import { ConnectivityService } from './connectivity.service';
import { ExecutionPayload, OutboxItem } from './models';
import { OutboxService } from './outbox.service';

/** Drains the IndexedDB outbox to the server. Safe by construction:
 *   - each item carries a stable Idempotency-Key, so replays never duplicate;
 *   - a 409 is surfaced as a conflict for human resolution, never overwritten;
 *   - failures stay queued and retry when connectivity returns. */
@Injectable({ providedIn: 'root' })
export class SyncService {
  private api = inject(ApiService);
  private outbox = inject(OutboxService);
  private conn = inject(ConnectivityService);

  private draining = false;
  private readonly inFlight = new Set<string>();
  private static readonly MAX_AUTO_ATTEMPTS = 4;

  readonly items = this.outbox.items;
  /** Items awaiting their first successful send (drives the auto-drain). */
  readonly pending = computed(
    () => this.items().filter((i) => i.status === 'pending').length,
  );
  /** Everything still needing attention — for badges/summaries. */
  readonly outstanding = computed(
    () =>
      this.items().filter(
        (i) => i.status === 'pending' || i.status === 'failed',
      ).length,
  );
  readonly conflicts = computed(
    () => this.items().filter((i) => i.status === 'conflict').length,
  );

  constructor() {
    // Auto-drain when connectivity returns. Only 'pending' items trigger this,
    // so a persistent server error can't create a retry storm — failed items
    // wait for an explicit retry.
    effect(() => {
      if (this.conn.online() && this.pending() > 0) {
        void this.syncAll();
      }
    });
  }

  async enqueue(label: string, payload: ExecutionPayload): Promise<OutboxItem> {
    const item: OutboxItem = {
      id: crypto.randomUUID(),
      idempotencyKey: crypto.randomUUID(),
      label,
      payload,
      status: 'pending',
      attempts: 0,
      createdAt: new Date().toISOString(),
    };
    await this.outbox.put(item);
    if (this.conn.online()) void this.syncItem(item);
    return item;
  }

  async syncAll(): Promise<void> {
    if (!this.conn.online() || this.draining) return;
    this.draining = true;
    try {
      for (const item of this.items()) {
        if (
          (item.status === 'pending' || item.status === 'failed') &&
          item.attempts < SyncService.MAX_AUTO_ATTEMPTS
        ) {
          await this.syncItem(item);
        }
      }
    } finally {
      this.draining = false;
    }
  }

  async syncItem(item: OutboxItem): Promise<void> {
    // Guard against the same item being submitted twice concurrently (e.g. a
    // manual resolve/retry racing the auto-sync effect) — that would race on the
    // idempotency key at the DB and could fail one of the two submits.
    if (!this.conn.online() || item.status === 'syncing' || this.inFlight.has(item.id)) return;
    this.inFlight.add(item.id);
    try {
      await this.outbox.put({ ...item, status: 'syncing' });
      const result = await firstValueFrom(
        this.api.submitExecution(item.payload, item.idempotencyKey),
      );
      await this.outbox.put({ ...item, status: 'synced', result, conflict: undefined });
    } catch (err) {
      const e = err as HttpErrorResponse;
      if (e.status === 409) {
        await this.outbox.put({
          ...item,
          status: 'conflict',
          attempts: item.attempts + 1,
          conflict: e.error?.detail,
        });
      } else {
        await this.outbox.put({
          ...item,
          status: 'failed',
          attempts: item.attempts + 1,
          lastError:
            e.error?.message ?? e.message ?? (e.status === 0 ? 'Network unavailable' : 'Sync failed'),
        });
      }
    } finally {
      this.inFlight.delete(item.id);
    }
  }

  async retry(item: OutboxItem): Promise<void> {
    await this.outbox.put({ ...item, status: 'pending', lastError: undefined });
    await this.syncItem({ ...item, status: 'pending' });
  }

  /** Resolve a conflict by adopting the server revision, then re-submitting
   *  under the same idempotency key (the server upserts the attempt). */
  async resolveWithServer(item: OutboxItem): Promise<void> {
    if (!item.conflict) return;
    const payload: ExecutionPayload = {
      ...item.payload,
      planRevision: item.conflict.serverRevision,
    };
    const next: OutboxItem = { ...item, payload, status: 'pending', conflict: undefined };
    await this.outbox.put(next);
    await this.syncItem(next);
  }

  /** Retry a failed evidence upload for an already-synced execution, then
   *  refresh the stored result so completeness updates in place. */
  async retryEvidence(item: OutboxItem, evidenceId: string): Promise<void> {
    if (!item.result) return;
    const result = await firstValueFrom(
      this.api.retryEvidence(item.result.id, evidenceId),
    );
    await this.outbox.put({ ...item, result });
  }

  async discard(item: OutboxItem): Promise<void> {
    await this.outbox.remove(item.id);
  }

  async clearSynced(): Promise<void> {
    await this.outbox.clearSynced();
  }
}
