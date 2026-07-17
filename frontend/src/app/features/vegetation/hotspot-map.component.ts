import {
  Component, ElementRef, OnDestroy, afterNextRender, effect, input, output, signal, viewChild,
} from '@angular/core';
import maplibregl, { GeoJSONSource, Map as MlMap } from 'maplibre-gl';

import { VegetationHotspot } from '../../core/models';

type FC = GeoJSON.FeatureCollection;
const EMPTY: FC = { type: 'FeatureCollection', features: [] };

// Heat ramp: cool (stable) → hot (reactive repeat). Interpolated by score 0–100.
const RAMP: [number, string][] = [
  [0, '#1f8a54'], [40, '#c9a227'], [66, '#e07b1a'], [85, '#c0392b'], [100, '#8e1a10'],
];

/** Hot-spotting heat layer over real corridor centerlines: line color + width
 *  scale with each span's reactive-repeat intensity, with the hottest spans as
 *  pulsing markers. Self-contained MapLibre style (no external tiles); the
 *  ranked list beside it (in the parent) is the non-map equivalent. */
@Component({
  selector: 'app-hotspot-map',
  standalone: true,
  template: `
    <div class="relative h-full w-full">
      <div #mapEl class="h-full w-full" role="application"
           aria-label="Hot-spotting intensity by corridor span. A ranked list of the same data is shown beside the map."></div>

      @if (hover(); as h) {
        <div class="pointer-events-none absolute z-10 rounded-md border border-border bg-surface px-2 py-1 text-xs shadow-pop"
             [style.left.px]="h.x + 10" [style.top.px]="h.y + 10">
          <div class="font-semibold text-ink">{{ h.circuit }} · {{ h.span }}</div>
          <div class="text-muted">hot-spot score {{ h.score }} · {{ h.tier }}</div>
        </div>
      }

      <div class="pointer-events-none absolute bottom-2 left-2 rounded-md border border-border bg-surface/90 p-2 text-xs shadow-card backdrop-blur">
        <div class="mb-1 font-semibold text-ink">Hot-spotting intensity</div>
        <div class="flex items-center gap-1">
          <span class="text-muted">stable</span>
          <span class="inline-block h-2.5 w-24 rounded-sm"
                style="background:linear-gradient(90deg,#1f8a54,#c9a227,#e07b1a,#c0392b,#8e1a10)"></span>
          <span class="text-muted">hot</span>
        </div>
      </div>
    </div>
  `,
})
export class HotspotMapComponent implements OnDestroy {
  ngOnDestroy(): void {
    // Release the WebGL context + listeners so revisiting the route can't
    // exhaust the browser's map-context budget.
    this.map?.remove();
    this.map = undefined;
  }

  readonly hotspots = input<VegetationHotspot[]>([]);
  readonly center = input<[number, number]>([-83.14, 40.13]);
  readonly spanClick = output<VegetationHotspot>();

  readonly hover = signal<{ x: number; y: number; circuit: string; span: string; score: number; tier: string } | null>(null);

  private mapEl = viewChild.required<ElementRef<HTMLDivElement>>('mapEl');
  private map?: MlMap;
  private ready = signal(false);
  private dark = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;

  constructor() {
    afterNextRender(() => this.initMap());
    effect(() => {
      const spans = this.hotspots();
      if (!this.ready() || !this.map) return;
      (this.map.getSource('spans') as GeoJSONSource | undefined)?.setData(this.fc(spans));
      this.fit(spans);
    });
  }

  private color(rawScore: number): string {
    // Clamp to the ramp's domain so an out-of-range score can't extrapolate the
    // interpolation past valid RGB (0–255).
    const score = Math.max(RAMP[0][0], Math.min(RAMP[RAMP.length - 1][0], rawScore));
    let lo = RAMP[0], hi = RAMP[RAMP.length - 1];
    for (let i = 0; i < RAMP.length - 1; i++) {
      if (score >= RAMP[i][0] && score <= RAMP[i + 1][0]) { lo = RAMP[i]; hi = RAMP[i + 1]; break; }
    }
    const t = hi[0] === lo[0] ? 0 : (score - lo[0]) / (hi[0] - lo[0]);
    return this.lerp(lo[1], hi[1], t);
  }
  private lerp(a: string, b: string, t: number): string {
    const pa = this.rgb(a), pb = this.rgb(b);
    const c = pa.map((v, i) => Math.round(v + (pb[i] - v) * t));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }
  private rgb(hex: string): number[] {
    const h = hex.replace('#', '');
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16));
  }

  private fc(spans: VegetationHotspot[]): FC {
    return {
      type: 'FeatureCollection',
      features: spans.filter((s) => s.geometry).map((s) => ({
        type: 'Feature',
        geometry: s.geometry as unknown as GeoJSON.Geometry,
        properties: {
          id: s.corridorId, circuit: s.circuit, span: s.spanLabel,
          score: s.hotspotScore, tier: s.tier, color: this.color(s.hotspotScore),
          width: 3 + (s.hotspotScore / 100) * 9,
        },
      })),
    };
  }
  private midpoints(spans: VegetationHotspot[]): FC {
    return {
      type: 'FeatureCollection',
      features: spans.filter((s) => s.geometry && s.tier === 'hot').map((s) => {
        const c = s.geometry!.coordinates;
        const mid = c[Math.floor(c.length / 2)];
        return {
          type: 'Feature',
          geometry: { type: 'Point', coordinates: mid } as GeoJSON.Point,
          properties: { color: this.color(s.hotspotScore), r: 6 + (s.hotspotScore / 100) * 6 },
        };
      }),
    };
  }

  private initMap(): void {
    this.map = new maplibregl.Map({
      container: this.mapEl().nativeElement,
      style: {
        version: 8, sources: {},
        layers: [{ id: 'bg', type: 'background', paint: { 'background-color': this.dark ? '#0e1512' : '#eef2ee' } }],
      },
      center: this.center(), zoom: 12, attributionControl: false,
    });
    this.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

    this.map.on('load', () => {
      const m = this.map!;
      m.addSource('spans', { type: 'geojson', data: EMPTY });
      m.addSource('hot', { type: 'geojson', data: EMPTY });
      // soft glow under the line
      m.addLayer({
        id: 'span-glow', type: 'line', source: 'spans',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': ['get', 'color'], 'line-width': ['*', ['get', 'width'], 2.2], 'line-opacity': 0.22, 'line-blur': 6 },
      });
      m.addLayer({
        id: 'span-line', type: 'line', source: 'spans',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': ['get', 'color'], 'line-width': ['get', 'width'] },
      });
      m.addLayer({
        id: 'hot-dot', type: 'circle', source: 'hot',
        paint: {
          'circle-radius': ['get', 'r'], 'circle-color': ['get', 'color'],
          'circle-opacity': 0.85, 'circle-stroke-color': '#fff', 'circle-stroke-width': 1.4,
        },
      });
      m.on('click', 'span-line', (e) => {
        const id = e.features?.[0]?.properties?.['id'];
        const span = this.hotspots().find((s) => s.corridorId === id);
        if (span) this.spanClick.emit(span);
      });
      m.on('mousemove', 'span-line', (e) => {
        const f = e.features?.[0]?.properties;
        m.getCanvas().style.cursor = 'pointer';
        if (f) this.hover.set({ x: e.point.x, y: e.point.y, circuit: String(f['circuit']), span: String(f['span']), score: Number(f['score']), tier: String(f['tier']) });
      });
      m.on('mouseleave', 'span-line', () => { m.getCanvas().style.cursor = ''; this.hover.set(null); });
      this.ready.set(true);
      (m.getSource('spans') as GeoJSONSource).setData(this.fc(this.hotspots()));
      (m.getSource('hot') as GeoJSONSource).setData(this.midpoints(this.hotspots()));
      this.fit(this.hotspots());
    });
  }

  private fit(spans: VegetationHotspot[]): void {
    const coords: number[][] = [];
    for (const s of spans) if (s.geometry) coords.push(...s.geometry.coordinates);
    if (this.map && this.ready()) (this.map.getSource('hot') as GeoJSONSource | undefined)?.setData(this.midpoints(spans));
    if (coords.length < 2) return;
    const lons = coords.map((c) => c[0]), lats = coords.map((c) => c[1]);
    this.map?.fitBounds(
      [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: 50, duration: 400, maxZoom: 14 },
    );
  }
}
