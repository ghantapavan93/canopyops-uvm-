import { Map as MlMap } from 'maplibre-gl';

/** Basemap options. `synthetic` keeps the app fully offline (no external tiles);
 *  `streets`/`satellite` overlay a real basemap under the synthetic operational
 *  layers when a connection is available. */
export type BasemapKind = 'synthetic' | 'streets' | 'satellite';

export const BASEMAPS: { key: BasemapKind; label: string }[] = [
  { key: 'synthetic', label: 'Synthetic' },
  { key: 'streets', label: 'Streets' },
  { key: 'satellite', label: 'Satellite' },
];

interface TileCfg { tiles: string[]; attribution: string; maxzoom: number; opacity: number }

const TILES: Record<Exclude<BasemapKind, 'synthetic'>, TileCfg> = {
  streets: {
    tiles: [
      'https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
      'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
      'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png',
    ],
    attribution: '© OpenStreetMap contributors',
    maxzoom: 19,
    opacity: 0.92,
  },
  satellite: {
    tiles: [
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    ],
    attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
    maxzoom: 19,
    opacity: 1,
  },
};

/** Add/remove a raster basemap beneath `beforeId` (the first operational layer),
 *  so synthetic corridors/zones always render on top of the real imagery. */
export function applyBasemap(map: MlMap, kind: BasemapKind, beforeId: string): void {
  if (map.getLayer('basemap')) map.removeLayer('basemap');
  if (map.getSource('basemap')) map.removeSource('basemap');
  if (kind === 'synthetic') return;
  const cfg = TILES[kind];
  map.addSource('basemap', {
    type: 'raster', tiles: cfg.tiles, tileSize: 256,
    attribution: cfg.attribution, maxzoom: cfg.maxzoom,
  });
  map.addLayer(
    { id: 'basemap', type: 'raster', source: 'basemap', paint: { 'raster-opacity': cfg.opacity } },
    map.getLayer(beforeId) ? beforeId : undefined,
  );
}
