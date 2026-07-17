import {
  Component,
  ElementRef,
  OnDestroy,
  afterNextRender,
  effect,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import maplibregl, { GeoJSONSource, Map as MlMap } from 'maplibre-gl';

import { RegionCell } from '../../core/models';

type FC = GeoJSON.FeatureCollection;
const EMPTY: FC = { type: 'FeatureCollection', features: [] };

// Sequential single-hue reds: light (few encroachments) → dark (many).
const RAMP = ['#fde5e3', '#f6b0ab', '#e97b73', '#d1453f', '#a11f1a'];

/** Choropleth of encroachments by service district. Self-contained MapLibre
 *  style (no external tiles). Data-driven fill, hover tooltip, click-to-filter,
 *  and an accessible legend. The ranked region list beside it (in the parent)
 *  is the non-map equivalent. */
@Component({
  selector: 'app-choropleth-map',
  standalone: true,
  template: `
    <div class="relative h-full w-full">
      <div #mapEl class="h-full w-full"
           role="application"
           aria-label="Encroachments by service district. A ranked list of the same data is shown beside the map."></div>

      <!-- hover tooltip -->
      @if (hover(); as h) {
        <div class="pointer-events-none absolute z-10 rounded-md border border-border bg-surface px-2 py-1 text-xs shadow-pop"
             [style.left.px]="h.x + 10" [style.top.px]="h.y + 10">
          <div class="font-semibold text-ink">{{ h.name }}</div>
          <div class="text-muted">{{ h.enc }} encroachments · {{ h.circuit }}</div>
        </div>
      }

      <!-- legend -->
      <div class="pointer-events-none absolute bottom-2 left-2 rounded-md border border-border bg-surface/90 p-2 text-xs shadow-card backdrop-blur">
        <div class="mb-1 font-semibold text-ink">Encroachments</div>
        <div class="flex items-center gap-1">
          <span class="text-muted">low</span>
          @for (c of ramp; track c) {
            <span class="inline-block h-2.5 w-4" [style.background]="c"></span>
          }
          <span class="text-muted">high</span>
        </div>
      </div>
    </div>
  `,
})
export class ChoroplethMapComponent implements OnDestroy {
  ngOnDestroy(): void {
    this.map?.remove();   // release the WebGL context + listeners on route change
    this.map = undefined;
  }

  readonly regions = input<RegionCell[]>([]);
  readonly maxValue = input<number>(1);
  readonly center = input<[number, number]>([-83.14, 40.13]);
  readonly regionClick = output<RegionCell>();

  readonly ramp = RAMP;
  readonly hover = signal<{ x: number; y: number; name: string; enc: number; circuit: string } | null>(null);

  private mapEl = viewChild.required<ElementRef<HTMLDivElement>>('mapEl');
  private map?: MlMap;
  private ready = signal(false);
  private dark = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;

  constructor() {
    afterNextRender(() => this.initMap());
    effect(() => {
      const regions = this.regions();
      if (!this.ready() || !this.map) return;
      (this.map.getSource('regions') as GeoJSONSource | undefined)?.setData(this.fc(regions));
      this.fit(regions);
    });
  }

  private color(value: number): string {
    const t = this.maxValue() ? value / this.maxValue() : 0;
    const i = Math.max(0, Math.min(RAMP.length - 1, Math.floor(t * RAMP.length)));
    return RAMP[i];
  }

  private fc(regions: RegionCell[]): FC {
    return {
      type: 'FeatureCollection',
      features: regions.map((r) => ({
        type: 'Feature',
        geometry: r.geometry as GeoJSON.Geometry,
        properties: {
          id: r.id, name: r.name, circuit: r.circuit,
          enc: r.encroachments, color: this.color(r.encroachments),
        },
      })),
    };
  }

  private initMap(): void {
    this.map = new maplibregl.Map({
      container: this.mapEl().nativeElement,
      style: {
        version: 8,
        sources: {},
        layers: [{ id: 'bg', type: 'background', paint: { 'background-color': this.dark ? '#0e1512' : '#eef2ee' } }],
      },
      center: this.center(),
      zoom: 11.4,
      attributionControl: false,
    });
    this.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');

    this.map.on('load', () => {
      const m = this.map!;
      m.addSource('regions', { type: 'geojson', data: EMPTY });
      m.addLayer({
        id: 'region-fill', type: 'fill', source: 'regions',
        paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.78 },
      });
      m.addLayer({
        id: 'region-line', type: 'line', source: 'regions',
        paint: { 'line-color': this.dark ? '#0e1512' : '#ffffff', 'line-width': 1.2 },
      });
      m.on('click', 'region-fill', (e) => {
        const id = e.features?.[0]?.properties?.['id'];
        const region = this.regions().find((r) => r.id === id);
        if (region) this.regionClick.emit(region);
      });
      m.on('mousemove', 'region-fill', (e) => {
        const f = e.features?.[0]?.properties;
        m.getCanvas().style.cursor = 'pointer';
        if (f) this.hover.set({ x: e.point.x, y: e.point.y, name: String(f['name']), enc: Number(f['enc']), circuit: String(f['circuit']) });
      });
      m.on('mouseleave', 'region-fill', () => {
        m.getCanvas().style.cursor = '';
        this.hover.set(null);
      });
      this.ready.set(true);
    });
  }

  private fit(regions: RegionCell[]): void {
    const coords: [number, number][] = [];
    for (const r of regions) {
      const rings = r.geometry?.coordinates as number[][][] | undefined;
      if (!rings) continue;   // skip a region with no polygon rather than throwing
      for (const ring of rings) {
        for (const p of ring) coords.push([p[0], p[1]]);
      }
    }
    if (coords.length < 2) return;
    const lons = coords.map((c) => c[0]), lats = coords.map((c) => c[1]);
    this.map?.fitBounds(
      [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: 30, duration: 400 },
    );
  }
}
