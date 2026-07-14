import { Component, computed, inject, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import {
  Corridor, EnvironmentalConstraint, TerrainGrid, TerrainProfile,
} from '../../core/models';
import { TerrainMeshComponent } from './terrain-mesh.component';

interface ChartPt { x: number; y: number; slope: number; steep: boolean }

@Component({
  selector: 'app-terrain',
  standalone: true,
  imports: [TerrainMeshComponent],
  templateUrl: './terrain.component.html',
})
export class TerrainComponent {
  private api = inject(ApiService);

  readonly terrain = signal<TerrainGrid | null>(null);
  readonly corridors = signal<Corridor[]>([]);
  readonly constraints = signal<EnvironmentalConstraint[]>([]);
  readonly crew = signal<[number, number]>([-83.175, 40.108]);

  readonly exaggeration = signal(2.2);
  readonly showWireframe = signal(false);
  readonly showZones = signal(true);

  readonly selectedCorridorId = signal<string | null>(null);
  readonly profile = signal<TerrainProfile | null>(null);

  readonly relief = computed(() => {
    const t = this.terrain();
    return t ? Math.round(t.maxElev - t.minElev) : 0;
  });

  /** Elevation profile scaled into a 0..100 × 0..40 SVG viewBox. */
  readonly chart = computed<{ pts: ChartPt[]; area: string; steepThreshold: number } | null>(() => {
    const p = this.profile();
    if (!p || !p.points.length) return null;
    const xs = p.points.map((q) => q.distanceM);
    const ys = p.points.map((q) => q.elevationM);
    const xMax = Math.max(...xs) || 1;
    const yMin = Math.min(...ys), yMax = Math.max(...ys);
    const yr = yMax - yMin || 1;
    const pts: ChartPt[] = p.points.map((q) => ({
      x: (q.distanceM / xMax) * 100,
      y: 38 - ((q.elevationM - yMin) / yr) * 34,
      slope: q.slopePct,
      steep: q.slopePct >= p.steepThresholdPct,
    }));
    const area = `M ${pts[0].x},40 ` + pts.map((q) => `L ${q.x.toFixed(2)},${q.y.toFixed(2)}`).join(' ')
      + ` L ${pts[pts.length - 1].x},40 Z`;
    return { pts, area, steepThreshold: p.steepThresholdPct };
  });

  constructor() {
    this.api.getTerrain(56, 34).subscribe((t) => this.terrain.set(t));
    this.api.listConstraints().subscribe((c) => this.constraints.set(c));
    this.api.listCorridors().subscribe((c) => {
      this.corridors.set(c);
      // Default to the ridge-crossing span so the steep-slope profile is visible.
      const preferred = c.find((x) => /ridge/i.test(x.spanLabel)) ?? c[0];
      if (preferred) this.selectCorridor(preferred.id);
    });
  }

  setExaggeration(v: number): void { this.exaggeration.set(v); }
  toggleWireframe(): void { this.showWireframe.update((v) => !v); }
  toggleZones(): void { this.showZones.update((v) => !v); }

  selectCorridor(id: string): void {
    this.selectedCorridorId.set(id);
    const c = this.corridors().find((x) => x.id === id);
    if (!c?.centerline) { this.profile.set(null); return; }
    this.api.terrainProfile(c.centerline, 48).subscribe((p) => this.profile.set(p));
  }

  selectedCorridor = computed(() => this.corridors().find((c) => c.id === this.selectedCorridorId()) ?? null);
}
