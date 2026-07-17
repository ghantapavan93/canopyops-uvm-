import {
  Component, ElementRef, OnDestroy, afterNextRender, effect, input, viewChild,
} from '@angular/core';

import { pointInGeometry } from '../../core/geofence';
import { Corridor, EnvironmentalConstraint, TerrainGrid } from '../../core/models';

type RGB = [number, number, number];

/** A self-contained interactive 3D terrain renderer — no WebGL library, no
 *  external tiles. Draws the DEM as a shaded surface (painter's algorithm +
 *  hillshade), drapes ROW corridors and protected zones onto it, and marks the
 *  crew position. Drag to orbit; vertical exaggeration is an input. */
@Component({
  selector: 'app-terrain-mesh',
  standalone: true,
  template: `<div #host class="relative h-full w-full touch-none">
    <canvas #cv class="h-full w-full cursor-grab active:cursor-grabbing"></canvas>
    <div class="pointer-events-none absolute bottom-2 left-2 rounded-md border border-border bg-surface/85 px-2 py-1 text-xs text-muted shadow-card backdrop-blur">
      Drag to orbit · {{ exaggeration() }}× vertical exaggeration
    </div>
  </div>`,
})
export class TerrainMeshComponent implements OnDestroy {
  readonly terrain = input<TerrainGrid | null>(null);
  readonly corridors = input<Corridor[]>([]);
  readonly constraints = input<EnvironmentalConstraint[]>([]);
  readonly crew = input<[number, number] | null>(null);
  readonly exaggeration = input(2.2);
  readonly showZones = input(true);
  readonly showWireframe = input(false);

  private host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private cv = viewChild.required<ElementRef<HTMLCanvasElement>>('cv');
  private ctx?: CanvasRenderingContext2D;
  private yaw = -0.5;
  private pitch = 0.95;
  private dragging = false;
  private lastX = 0;
  private lastY = 0;
  private zoneTint: (RGB | null)[][] = [];

  constructor() {
    afterNextRender(() => this.setup());
    effect(() => {
      // Re-derive per-cell zone tint (rotation-independent) then redraw.
      this.terrain(); this.constraints(); this.showZones();
      this.computeZoneTint();
      this.exaggeration(); this.showWireframe(); this.corridors(); this.crew();
      this.render();
    });
  }

  private _onResize = () => { this.resize(); this.render(); };

  ngOnDestroy(): void {
    window.removeEventListener('resize', this._onResize);   // no orphaned window listener per visit
  }

  private setup(): void {
    const cv = this.cv().nativeElement;
    this.ctx = cv.getContext('2d') ?? undefined;
    this.resize();
    window.addEventListener('resize', this._onResize);

    cv.addEventListener('pointerdown', (e) => {
      this.dragging = true; this.lastX = e.clientX; this.lastY = e.clientY;
      cv.setPointerCapture(e.pointerId);
    });
    cv.addEventListener('pointermove', (e) => {
      if (!this.dragging) return;
      this.yaw += (e.clientX - this.lastX) * 0.008;
      this.pitch = Math.max(0.2, Math.min(1.45, this.pitch - (e.clientY - this.lastY) * 0.006));
      this.lastX = e.clientX; this.lastY = e.clientY;
      this.render();
    });
    const stop = () => { this.dragging = false; };
    cv.addEventListener('pointerup', stop);
    cv.addEventListener('pointercancel', stop);
    this.render();
  }

  private resize(): void {
    const host = this.host().nativeElement;
    const cv = this.cv().nativeElement;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.max(1, Math.floor(host.clientWidth * dpr));
    cv.height = Math.max(1, Math.floor(host.clientHeight * dpr));
  }

  // --- geometry helpers ---
  private sampleElev(u: number, v: number): number {
    const t = this.terrain()!;
    const fc = Math.max(0, Math.min(t.cols - 1, u * (t.cols - 1)));
    const fr = Math.max(0, Math.min(t.rows - 1, v * (t.rows - 1)));
    const c0 = Math.floor(fc), r0 = Math.floor(fr);
    const c1 = Math.min(t.cols - 1, c0 + 1), r1 = Math.min(t.rows - 1, r0 + 1);
    const tx = fc - c0, ty = fr - r0;
    const top = t.elevations[r0][c0] * (1 - tx) + t.elevations[r0][c1] * tx;
    const bot = t.elevations[r1][c0] * (1 - tx) + t.elevations[r1][c1] * tx;
    return top * (1 - ty) + bot * ty;
  }

  private computeZoneTint(): void {
    const t = this.terrain();
    this.zoneTint = [];
    if (!t || !this.showZones()) return;
    const [minLon, minLat, maxLon, maxLat] = t.bbox;
    const zones = this.constraints().filter(
      (z) => z.geometry?.type === 'Polygon' || z.geometry?.type === 'MultiPolygon');
    for (let i = 0; i < t.rows - 1; i++) {
      const row: (RGB | null)[] = [];
      for (let j = 0; j < t.cols - 1; j++) {
        const u = (j + 0.5) / (t.cols - 1), v = (i + 0.5) / (t.rows - 1);
        const lon = minLon + u * (maxLon - minLon), lat = minLat + v * (maxLat - minLat);
        let tint: RGB | null = null;
        for (const z of zones) {
          if (pointInGeometry(lon, lat, z.geometry!)) {
            tint = z.severity === 'blocking' ? [180, 35, 31] : [168, 114, 10];
            break;
          }
        }
        row.push(tint);
      }
      this.zoneTint.push(row);
    }
  }

  private elevColor(f: number): RGB {
    const stops: [number, RGB][] = [
      [0.0, [76, 122, 84]], [0.4, [150, 140, 96]], [0.7, [128, 104, 84]], [1.0, [235, 236, 240]],
    ];
    for (let k = 1; k < stops.length; k++) {
      if (f <= stops[k][0]) {
        const [f0, c0] = stops[k - 1], [f1, c1] = stops[k];
        const tt = (f - f0) / (f1 - f0 || 1);
        return [0, 1, 2].map((n) => Math.round(c0[n] + (c1[n] - c0[n]) * tt)) as RGB;
      }
    }
    return stops[stops.length - 1][1];
  }

  private render(): void {
    const ctx = this.ctx, t = this.terrain();
    if (!ctx) return;
    const cv = this.cv().nativeElement;
    ctx.clearRect(0, 0, cv.width, cv.height);
    if (!t) return;

    const w = cv.width, h = cv.height;
    const spanX = 1, spanY = 0.55, zH = 0.30;
    const rel = (t.maxElev - t.minElev) || 1;
    const cosY = Math.cos(this.yaw), sinY = Math.sin(this.yaw);
    const cosP = Math.cos(this.pitch), sinP = Math.sin(this.pitch);
    const scale = Math.min(w / (spanX * 1.7), h / (spanX * 1.15));
    const cx = w / 2, cy = h * 0.58;
    const exag = this.exaggeration();

    const proj = (u: number, v: number, elev: number) => {
      const x = (u - 0.5) * spanX, y = (v - 0.5) * spanY;
      const z = ((elev - t.minElev) / rel - 0.5) * zH * exag;
      const x1 = x * cosY - y * sinY, y1 = x * sinY + y * cosY;
      const y2 = y1 * cosP - z * sinP, z2 = y1 * sinP + z * cosP;
      return { sx: cx + x1 * scale, sy: cy - z2 * scale, depth: y2 };
    };

    // vertex projections
    const P: { sx: number; sy: number; depth: number }[][] = [];
    for (let i = 0; i < t.rows; i++) {
      const row = [];
      for (let j = 0; j < t.cols; j++) row.push(proj(j / (t.cols - 1), i / (t.rows - 1), t.elevations[i][j]));
      P.push(row);
    }

    // light direction (normalized) for hillshade
    const L = ((): RGB => { const v: RGB = [-0.5, 0.6, 0.7]; const m = Math.hypot(...v); return v.map((n) => n / m) as RGB; })();

    interface Quad { pts: { sx: number; sy: number }[]; depth: number; color: string }
    const quads: Quad[] = [];
    for (let i = 0; i < t.rows - 1; i++) {
      for (let j = 0; j < t.cols - 1; j++) {
        const a = P[i][j], b = P[i][j + 1], c = P[i + 1][j + 1], d = P[i + 1][j];
        const e00 = t.elevations[i][j], e10 = t.elevations[i][j + 1], e01 = t.elevations[i + 1][j];
        const n: RGB = [-(e10 - e00), -(e01 - e00), 10];
        const nm = Math.hypot(...n);
        const shade = Math.max(0.2, Math.min(1, 0.25 + 0.85 * ((n[0] * L[0] + n[1] * L[1] + n[2] * L[2]) / (nm || 1))));
        const avgE = (e00 + e10 + e01 + t.elevations[i + 1][j + 1]) / 4;
        let col = this.elevColor((avgE - t.minElev) / rel);
        const tint = this.zoneTint[i]?.[j];
        if (tint) col = [0, 1, 2].map((k) => Math.round(col[k] * 0.45 + tint[k] * 0.55)) as RGB;
        const rgb = col.map((v) => Math.round(v * shade));
        quads.push({ pts: [a, b, c, d], depth: (a.depth + b.depth + c.depth + d.depth) / 4, color: `rgb(${rgb[0]},${rgb[1]},${rgb[2]})` });
      }
    }
    quads.sort((p, q) => q.depth - p.depth); // far → near

    const wire = this.showWireframe();
    for (const q of quads) {
      ctx.beginPath();
      ctx.moveTo(q.pts[0].sx, q.pts[0].sy);
      for (let k = 1; k < 4; k++) ctx.lineTo(q.pts[k].sx, q.pts[k].sy);
      ctx.closePath();
      ctx.fillStyle = q.color;
      ctx.fill();
      if (wire) { ctx.strokeStyle = 'rgba(255,255,255,0.15)'; ctx.lineWidth = 0.5; ctx.stroke(); }
    }

    // drape corridors (bright polyline at terrain elevation)
    const [minLon, minLat, maxLon, maxLat] = t.bbox;
    const toUV = (lon: number, lat: number): [number, number] =>
      [(lon - minLon) / (maxLon - minLon), (lat - minLat) / (maxLat - minLat)];
    ctx.lineWidth = 2; ctx.strokeStyle = '#f2c14e';
    for (const c of this.corridors()) {
      const coords = c.centerline?.coordinates as unknown as number[][] | undefined;
      if (!coords) continue;
      ctx.beginPath();
      coords.forEach(([lon, lat], k) => {
        const [u, v] = toUV(lon, lat);
        const p = proj(u, v, this.sampleElev(u, v));
        k ? ctx.lineTo(p.sx, p.sy) : ctx.moveTo(p.sx, p.sy);
      });
      ctx.stroke();
    }

    // crew marker
    const crew = this.crew();
    if (crew) {
      const [u, v] = toUV(crew[0], crew[1]);
      const p = proj(u, v, this.sampleElev(u, v));
      ctx.beginPath(); ctx.arc(p.sx, p.sy, 6, 0, Math.PI * 2);
      ctx.fillStyle = '#1f5fa8'; ctx.fill();
      ctx.lineWidth = 2; ctx.strokeStyle = '#fff'; ctx.stroke();
    }
  }
}
