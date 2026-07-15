import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import {
  CycleBusterBoard, CyclePriority, HotspotBoard, VegetationHotspot,
} from '../../core/models';
import { HotspotMapComponent } from './hotspot-map.component';

/** Vegetation Intelligence — two Davey/DRG UVM concepts made concrete:
 *  a hot-spotting heat layer (reactive repeat work to eliminate) and a
 *  cycle-buster watchlist (fast-regrowth spans that break the trim cycle). */
@Component({
  selector: 'app-vegetation',
  standalone: true,
  imports: [HotspotMapComponent, DatePipe],
  templateUrl: './vegetation.component.html',
})
export class VegetationComponent {
  private api = inject(ApiService);

  readonly hotspots = signal<HotspotBoard | null>(null);
  readonly cycles = signal<CycleBusterBoard | null>(null);
  readonly selected = signal<VegetationHotspot | null>(null);
  readonly onlyBusters = signal(false);

  readonly hotCells = computed(() => this.hotspots()?.hotspots ?? []);
  readonly spans = computed(() => {
    const all = this.cycles()?.spans ?? [];
    return this.onlyBusters() ? all.filter((s) => s.isCycleBuster) : all;
  });

  constructor() {
    this.api.getHotspots().subscribe((b) => this.hotspots.set(b));
    this.api.getCycleBusters().subscribe((b) => this.cycles.set(b));
  }

  pick(s: VegetationHotspot): void {
    this.selected.set(this.selected()?.corridorId === s.corridorId ? null : s);
  }
  toggleBusters(): void { this.onlyBusters.update((v) => !v); }

  tierColor(tier: string): string {
    return tier === 'hot' ? '#c0392b' : tier === 'elevated' ? '#e07b1a' : '#1f8a54';
  }
  priorityClass(p: CyclePriority): string {
    return p === 'hazard' ? 'bg-danger-soft text-danger'
      : p === 'elevated' ? 'bg-warn-soft text-warn' : 'bg-surface-2 text-muted';
  }
  // rough calendar for the countdown (days → months, no external dep)
  months(days: number): string {
    return days >= 365 ? `~${(days / 365).toFixed(1)} yr` : `~${Math.round(days / 30)} mo`;
  }
  // fuller bar = sooner conflict (worse); scaled against a ~2yr (730d) horizon
  conflictBar(days: number): number {
    return Math.max(6, 100 - (days / 730) * 100);
  }
}
