import {
  Component, ElementRef, OnDestroy, afterNextRender, effect, input, output, signal, viewChild,
} from '@angular/core';
import maplibregl, { GeoJSONSource, Map as MlMap, Marker } from 'maplibre-gl';

import { Corridor, EnvironmentalConstraint, ProximityLevel } from '../../core/models';
import { BASEMAPS, BasemapKind, applyBasemap } from '../../shared/charts/basemap';

type FC = GeoJSON.FeatureCollection;
const EMPTY: FC = { type: 'FeatureCollection', features: [] };

const LEVEL_HEX: Record<ProximityLevel, string> = {
  breach: '#b4231f',
  entered: '#d1663f',
  warning: '#a8720a',
  clear: '#1f6f4b',
};

/** Field-safety map: protected zones coloured by live alert level, a detection
 *  radius, and a draggable crew position that emits on move/click. Self-contained
 *  MapLibre style (no external tiles) so it works offline. */
@Component({
  selector: 'app-geofence-map',
  standalone: true,
  template: `<div class="relative h-full w-full">
    <div #mapEl class="h-full w-full" role="application"
         aria-label="Field-safety map. Drag the crew marker or click to move it."></div>
    <div class="absolute right-2 top-2 z-10 flex overflow-hidden rounded-md border border-border bg-surface/95 text-[11px] shadow-card backdrop-blur">
      @for (b of basemaps; track b.key) {
        <button type="button" (click)="basemap.set(b.key)" [attr.aria-pressed]="basemap() === b.key"
                class="px-2 py-1 font-medium transition-colors"
                [class.bg-primary]="basemap() === b.key" [class.text-primary-ink]="basemap() === b.key"
                [class.text-muted]="basemap() !== b.key">{{ b.label }}</button>
      }
    </div>
    <div class="pointer-events-none absolute bottom-2 left-2 z-10 rounded-md border border-border bg-surface/90 px-2 py-1 text-[11px] text-muted shadow-card backdrop-blur">
      Drag the crew marker — or click the map — to move. Detection radius {{ warningMeters() }} m.
    </div>
  </div>`,
})
export class GeofenceMapComponent implements OnDestroy {
  ngOnDestroy(): void {
    this.map?.remove();   // release the WebGL context + listeners on route change
    this.map = undefined;
  }

  readonly constraints = input<EnvironmentalConstraint[]>([]);
  readonly corridors = input<Corridor[]>([]);
  readonly position = input.required<[number, number]>();
  readonly warningMeters = input(100);
  readonly levels = input<Record<string, ProximityLevel>>({});
  readonly positionChange = output<[number, number]>();

  readonly basemaps = BASEMAPS;
  readonly basemap = signal<BasemapKind>('synthetic');

  private mapEl = viewChild.required<ElementRef<HTMLDivElement>>('mapEl');
  private map?: MlMap;
  private marker?: Marker;
  private ready = false;
  private readyTick = signal(0);
  private dark = window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;

  constructor() {
    afterNextRender(() => this.initMap());
    effect(() => {
      const pos = this.position();
      const constraints = this.constraints();
      const corridors = this.corridors();
      const levels = this.levels();
      const warn = this.warningMeters();
      if (!this.ready || !this.map) return;
      this.setSrc('corridors', this.corridorFC(corridors));
      this.setSrc('zones', this.zoneFC(constraints, levels));
      this.setSrc('detection', this.circleFC(pos, warn));
      this.marker?.setLngLat(pos);
    });
    effect(() => {
      const kind = this.basemap();
      this.readyTick();
      if (!this.ready || !this.map) return;
      applyBasemap(this.map, kind, 'detection-line');
    });
  }

  private setSrc(id: string, data: FC): void {
    (this.map?.getSource(id) as GeoJSONSource | undefined)?.setData(data);
  }

  private zoneFC(constraints: EnvironmentalConstraint[], levels: Record<string, ProximityLevel>): FC {
    return {
      type: 'FeatureCollection',
      features: constraints.filter((c) => c.geometry).map((c) => ({
        type: 'Feature',
        geometry: c.geometry as GeoJSON.Geometry,
        properties: { level: levels[c.id] ?? 'clear', name: c.name },
      })),
    };
  }
  private corridorFC(corridors: Corridor[]): FC {
    return {
      type: 'FeatureCollection',
      features: corridors.filter((c) => c.centerline).map((c) => ({
        type: 'Feature', geometry: c.centerline as GeoJSON.Geometry, properties: {},
      })),
    };
  }

  /** Approximate a geodesic circle (metres) as a polygon ring for the map. */
  private circleFC([lon, lat]: [number, number], radiusM: number): FC {
    const pts: [number, number][] = [];
    const dLat = radiusM / 110540;
    const dLon = radiusM / (111320 * Math.cos((lat * Math.PI) / 180));
    for (let i = 0; i <= 48; i++) {
      const a = (i / 48) * 2 * Math.PI;
      pts.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
    }
    return { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'Polygon', coordinates: [pts] }, properties: {} }] };
  }

  private initMap(): void {
    const m = (this.map = new maplibregl.Map({
      container: this.mapEl().nativeElement,
      style: {
        version: 8, sources: {},
        layers: [{ id: 'bg', type: 'background', paint: { 'background-color': this.dark ? '#0e1512' : '#eef2ee' } }],
      },
      center: this.position(), zoom: 13.5, attributionControl: false,
    }));
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    m.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');

    // Crew marker — a pulsing dot; draggable.
    const el = document.createElement('div');
    el.style.cssText = 'width:18px;height:18px;border-radius:50%;background:#1f5fa8;border:3px solid #fff;box-shadow:0 0 0 4px rgba(31,95,168,.35);cursor:grab;';
    this.marker = new maplibregl.Marker({ element: el, draggable: true })
      .setLngLat(this.position())
      .addTo(m);
    this.marker.on('dragend', () => {
      const { lng, lat } = this.marker!.getLngLat();
      this.positionChange.emit([+lng.toFixed(5), +lat.toFixed(5)]);
    });

    m.on('load', () => {
      for (const id of ['corridors', 'zones', 'detection']) {
        m.addSource(id, { type: 'geojson', data: EMPTY });
      }
      // Detection radius (dashed ring).
      m.addLayer({ id: 'detection-line', type: 'line', source: 'detection',
        paint: { 'line-color': this.dark ? '#5b9be0' : '#1f5fa8', 'line-width': 1.5, 'line-dasharray': [2, 2] } });
      // Zones filled + outlined, coloured by live alert level.
      const colour = ['match', ['get', 'level'],
        'breach', LEVEL_HEX.breach, 'entered', LEVEL_HEX.entered,
        'warning', LEVEL_HEX.warning, LEVEL_HEX.clear] as unknown as maplibregl.ExpressionSpecification;
      m.addLayer({ id: 'zone-fill', type: 'fill', source: 'zones',
        paint: { 'fill-color': colour, 'fill-opacity': 0.28 } });
      m.addLayer({ id: 'zone-line', type: 'line', source: 'zones',
        paint: { 'line-color': colour, 'line-width': 2 } });
      m.addLayer({ id: 'corridor-line', type: 'line', source: 'corridors',
        paint: { 'line-color': this.dark ? '#9db0a5' : '#5b6b62', 'line-width': 2, 'line-opacity': 0.6 } });

      m.on('click', (e) => {
        this.positionChange.emit([+e.lngLat.lng.toFixed(5), +e.lngLat.lat.toFixed(5)]);
      });

      this.ready = true;
      this.readyTick.set(1);   // let the basemap effect apply once layers exist
      // Prime the sources now that layers exist.
      this.setSrc('corridors', this.corridorFC(this.corridors()));
      this.setSrc('zones', this.zoneFC(this.constraints(), this.levels()));
      this.setSrc('detection', this.circleFC(this.position(), this.warningMeters()));
    });
  }
}
