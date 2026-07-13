import { Component, inject } from '@angular/core';
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

@Component({
  selector: 'app-sync-center',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './sync-center.component.html',
})
export class SyncCenterComponent {
  sync = inject(SyncService);
  conn = inject(ConnectivityService);
  private api = inject(ApiService);

  readonly meta = OUTBOX_META;
  readonly items = this.sync.items;

  chip(status: OutboxStatus): string {
    return TONE_CHIP[OUTBOX_META[status].tone];
  }

  pct(v: number): string {
    return `${Math.round(v * 100)}%`;
  }

  simulateEdit(item: OutboxItem): void {
    // Stand-in for a manager editing the plan on another device while this
    // execution sits in the outbox. Bumps server revision -> next sync conflicts.
    this.api.bumpPlanRevision(item.payload.planId).subscribe();
  }
}
