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

import { Corridor, Geometry } from '../../core/models';
import { BASEMAPS, BasemapKind, applyBasemap } from './basemap';

type FC = GeoJSON.FeatureCollection;
const EMPTY: FC = { type: 'FeatureCollection', features: [] };

/** Click-to-draw a polygon on a MapLibre map. Optionally shows corridors, a
 *  planned polygon (dashed outline) and an actual/completed polygon (fill) as
 *  reference context — so a reviewer can draw only the rework area over the
 *  planned-vs-completed picture. Self-contained style, no external tiles. */
@Component({
  selector: 'app-polygon-draw-map',
  standalone: true,
  template: `
    <div class="relative h-full w-full">
      <div #mapEl class="h-full w-full" role="application"
           aria-label="Draw the area by clicking to place polygon corners."></div>

      <div class="absolute left-2 top-2 z-10 flex items-center gap-1.5 rounded-md border border-border bg-surface/95 px-2 py-1 text-xs shadow-card">
        <span class="font-medium text-ink">{{ points().length }} pts</span>
        <button (click)="undo()" [disabled]="!points().length"
                class="rounded border border-border px-1.5 py-0.5 text-muted hover:bg-surface-2 disabled:opacity-40">Undo</button>
        <button (click)="clear()" [disabled]="!points().length"
                class="rounded border border-border px-1.5 py-0.5 text-muted hover:bg-surface-2 disabled:opacity-40">Clear</button>
      </div>

      <div class="absolute right-2 top-2 z-10 flex overflow-hidden rounded-md border border-border bg-surface/95 text-[10px] shadow-card backdrop-blur">
        @for (b of basemaps; track b.key) {
          <button (click)="basemap.set(b.key)" [attr.aria-pressed]="basemap() === b.key"
                  class="px-1.5 py-0.5 font-medium transition-colors"
                  [class.bg-primary]="basemap() === b.key" [class.text-primary-ink]="basemap() === b.key"
                  [class.text-muted]="basemap() !== b.key">{{ b.label }}</button>
        }
      </div>

      @if (plannedGeometry() || actualGeometry()) {
        <div class="pointer-events-none absolute right-2 top-9 z-10 rounded-md border border-border bg-surface/90 p-1.5 text-[10px] shadow-card backdrop-blur">
          @if (plannedGeometry()) { <div class="flex items-center gap-1"><span class="inline-block h-0 w-3 border-t-2 border-dashed" style="border-color:#1f5fa8"></span>Planned</div> }
          @if (actualGeometry()) { <div class="flex items-center gap-1"><span class="inline-block h-2.5 w-3" style="background:rgba(31,138,84,.35)"></span>Completed</div> }
          <div class="flex items-center gap-1"><span class="inline-block h-2.5 w-3" [style.background]="drawFillRgba()"></span>Your draw</div>
        </div>
      }

      <div class="pointer-events-none absolute bottom-2 left-2 z-10 rounded-md border border-border bg-surface/90 px-2 py-1 text-[11px] text-muted shadow-card backdrop-blur">
        @if (points().length < 3) { Click the map to place at least 3 corners. }
        @else { {{ points().length }}-sided area drawn. }
      </div>
    </div>
  `,
})
export class PolygonDrawMapComponent implements OnDestroy {
  ngOnDestroy(): void {
    this.map?.remove();   // release the WebGL context + listeners on route change
    this.map = undefined;
  }

  readonly corridors = input<Corridor[]>([]);
  readonly center = input<[number, number]>([-83.14, 40.11]);
  readonly plannedGeometry = input<Geometry | null>(null);
  readonly actualGeometry = input<Geometry | null>(null);
  readonly drawColor = input<string>('#1f8a54'); // green by default; red for rework
  /** When set, the map flies to this corridor (unless the user is mid-draw). */
  readonly focusCorridorId = input<string | null>(null);
  readonly geometryChange = output<Geometry | null>();

  readonly points = signal<[number, number][]>([]);
  readonly basemaps = BASEMAPS;
  readonly basemap = signal<BasemapKind>('synthetic');

  private mapEl = viewChild.required<ElementRef<HTMLDivElement>>('mapEl');
  private map?: MlMap;
  private ready = signal(false);
  private dark = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;

  constructor() {
    afterNextRender(() => this.initMap());
    effect(() => {
      const kind = this.basemap();
      if (!this.ready() || !this.map) return;
      applyBasemap(this.map, kind, 'corridor-line');
    });
    effect(() => {
      const corridors = this.corridors();
      const pts = this.points();
      const planned = this.plannedGeometry();
      const actual = this.actualGeometry();
      const focusId = this.focusCorridorId();
      if (!this.ready() || !this.map) return;
      this.setSrc('corridors', this.corridorFC(corridors));
      this.setSrc('focus', this.singleFC(this.corridorGeom(corridors, focusId)));
      this.setSrc('planned', this.singleFC(planned));
      this.setSrc('actual', this.singleFC(actual));
      this.setSrc('draw-fill', this.polygonFC(pts));
      this.setSrc('draw-line', this.lineFC(pts));
      this.setSrc('draw-verts', this.vertFC(pts));
      // Fit priority: user draw context (planned) > selected corridor. Never
      // yank the camera while the user is actively placing corners.
      if (planned && !pts.length) this.fitTo(planned);
      else if (focusId && !pts.length) {
        const g = this.corridorGeom(corridors, focusId);
        if (g) this.fitToCoords(this.flatCoords(g));
      }
    });
  }

  drawFillRgba(): string {
    return `${this.drawColor()}59`; // ~35% alpha hex
  }

  undo(): void {
    this.points.update((p) => p.slice(0, -1));
    this.emit();
  }
  clear(): void {
    this.points.set([]);
    this.emit();
  }

  private emit(): void {
    const p = this.points();
    this.geometryChange.emit(
      p.length >= 3 ? { type: 'Polygon', coordinates: [[...p, p[0]]] } : null,
    );
  }

  private setSrc(id: string, data: FC): void {
    (this.map?.getSource(id) as GeoJSONSource | undefined)?.setData(data);
  }

  private singleFC(g: Geometry | null): FC {
    return g
      ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: g as GeoJSON.Geometry, properties: {} }] }
      : EMPTY;
  }
  private corridorFC(corridors: Corridor[]): FC {
    return {
      type: 'FeatureCollection',
      features: corridors.filter((c) => c.centerline).map((c) => ({
        type: 'Feature', geometry: c.centerline as GeoJSON.Geometry, properties: {},
      })),
    };
  }
  private polygonFC(pts: [number, number][]): FC {
    if (pts.length < 3) return EMPTY;
    return { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Polygon', coordinates: [[...pts, pts[0]]] }, properties: {} }] };
  }
  private lineFC(pts: [number, number][]): FC {
    if (pts.length < 2) return EMPTY;
    const coords = pts.length >= 3 ? [...pts, pts[0]] : pts;
    return { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'LineString', coordinates: coords }, properties: {} }] };
  }
  private vertFC(pts: [number, number][]): FC {
    return { type: 'FeatureCollection', features: pts.map((p) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: p }, properties: {} })) };
  }

  private corridorGeom(corridors: Corridor[], id: string | null): Geometry | null {
    if (!id) return null;
    const c = corridors.find((x) => x.id === id);
    return (c?.centerline as Geometry | undefined) ?? null;
  }

  /** Flatten Polygon (number[][][]) or LineString (number[][]) coords to points. */
  private flatCoords(g: Geometry): [number, number][] {
    const out: [number, number][] = [];
    const c = g.coordinates as unknown;
    const walk = (a: any): void => {
      if (Array.isArray(a) && typeof a[0] === 'number') out.push([a[0], a[1]]);
      else if (Array.isArray(a)) a.forEach(walk);
    };
    walk(c);
    return out;
  }

  private fitTo(g: Geometry): void {
    this.fitToCoords(this.flatCoords(g));
  }

  private fitToCoords(coords: [number, number][]): void {
    if (coords.length < 2) return;
    const lons = coords.map((c) => c[0]), lats = coords.map((c) => c[1]);
    this.map?.fitBounds(
      [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: 60, maxZoom: 15, duration: 400 },
    );
  }

  private initMap(): void {
    const draw = this.drawColor();
    this.map = new maplibregl.Map({
      container: this.mapEl().nativeElement,
      style: {
        version: 8, sources: {},
        layers: [{ id: 'bg', type: 'background', paint: { 'background-color': this.dark ? '#0e1512' : '#eef2ee' } }],
      },
      center: this.center(), zoom: 13, attributionControl: false,
    });
    this.map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    this.map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
    this.map.on('load', () => {
      const m = this.map!;
      for (const id of ['corridors', 'focus', 'planned', 'actual', 'draw-fill', 'draw-line', 'draw-verts']) {
        m.addSource(id, { type: 'geojson', data: EMPTY });
      }
      m.addLayer({ id: 'corridor-line', type: 'line', source: 'corridors',
        paint: { 'line-color': this.dark ? '#9db0a5' : '#5b6b62', 'line-width': 2, 'line-opacity': 0.6 } });
      // the currently-selected corridor, emphasized
      m.addLayer({ id: 'focus-line', type: 'line', source: 'focus',
        paint: { 'line-color': this.dark ? '#37b57e' : '#1f6f4b', 'line-width': 5, 'line-opacity': 0.9 } });
      // planned = dashed blue outline; actual/completed = green fill
      m.addLayer({ id: 'actual-fill', type: 'fill', source: 'actual', paint: { 'fill-color': '#1f8a54', 'fill-opacity': 0.28 } });
      m.addLayer({ id: 'actual-line', type: 'line', source: 'actual', paint: { 'line-color': '#1f8a54', 'line-width': 1.5 } });
      m.addLayer({ id: 'planned-line', type: 'line', source: 'planned', paint: { 'line-color': '#1f5fa8', 'line-width': 2, 'line-dasharray': [2, 2] } });
      // the reviewer's / manager's own draw (color configurable)
      m.addLayer({ id: 'draw-fill-l', type: 'fill', source: 'draw-fill', paint: { 'fill-color': draw, 'fill-opacity': 0.3 } });
      m.addLayer({ id: 'draw-line-l', type: 'line', source: 'draw-line', paint: { 'line-color': draw, 'line-width': 2 } });
      m.addLayer({ id: 'draw-verts-l', type: 'circle', source: 'draw-verts',
        paint: { 'circle-radius': 4, 'circle-color': '#ffffff', 'circle-stroke-color': draw, 'circle-stroke-width': 2 } });

      m.on('click', (e) => {
        this.points.update((p) => [...p, [+e.lngLat.lng.toFixed(5), +e.lngLat.lat.toFixed(5)]]);
        this.emit();
      });
      this.ready.set(true);
    });
  }
}
