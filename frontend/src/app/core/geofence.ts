import {
  EnvironmentalConstraint, Geometry, ProximityLevel, ProximityResult, ProximityZone,
} from './models';

/** Pure, dependency-free geofence math — the on-device fallback that mirrors the
 *  server's PostGIS proximity check, so alerts keep working with no connectivity
 *  and offline results match what the API would return. */

const RANK: Record<ProximityLevel, number> = { clear: 0, warning: 1, entered: 2, breach: 3 };

/** Ray-casting point-in-polygon over a single ring [[lon,lat], ...]. */
export function pointInRing(lon: number, lat: number, ring: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];
    const intersect = (yi > lat) !== (yj > lat)
      && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

/** Polygon (first ring outer; remaining rings are holes). */
export function pointInPolygon(lon: number, lat: number, polygon: number[][][]): boolean {
  if (!polygon.length || !pointInRing(lon, lat, polygon[0])) return false;
  for (let h = 1; h < polygon.length; h++) {
    if (pointInRing(lon, lat, polygon[h])) return false; // inside a hole
  }
  return true;
}

/** Metres between two lon/lat points (equirectangular approximation — accurate
 *  at the small distances a geofence cares about). */
export function haversineMeters(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const R = 6371000;
  const rad = Math.PI / 180;
  const x = (lon2 - lon1) * rad * Math.cos(((lat1 + lat2) / 2) * rad);
  const y = (lat2 - lat1) * rad;
  return Math.sqrt(x * x + y * y) * R;
}

/** Shortest distance (m) from a point to a segment, projected locally to metres. */
function pointToSegmentMeters(lon: number, lat: number, a: number[], b: number[]): number {
  const rad = Math.PI / 180;
  const mPerDegLat = 111320;
  const mPerDegLon = 111320 * Math.cos(lat * rad);
  const px = (lon - a[0]) * mPerDegLon, py = (lat - a[1]) * mPerDegLat;
  const bx = (b[0] - a[0]) * mPerDegLon, by = (b[1] - a[1]) * mPerDegLat;
  const len2 = bx * bx + by * by;
  const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, (px * bx + py * by) / len2));
  const dx = px - t * bx, dy = py - t * by;
  return Math.sqrt(dx * dx + dy * dy);
}

function distanceToRingsMeters(lon: number, lat: number, polygon: number[][][]): number {
  if (pointInPolygon(lon, lat, polygon)) return 0;
  let min = Infinity;
  for (const ring of polygon) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      min = Math.min(min, pointToSegmentMeters(lon, lat, ring[j], ring[i]));
    }
  }
  return min;
}

/** Inside test for a Polygon OR MultiPolygon (parity with PostGIS ST_Contains). */
export function pointInGeometry(lon: number, lat: number, geometry: Geometry): boolean {
  if (geometry.type === 'Polygon') {
    return pointInPolygon(lon, lat, geometry.coordinates as unknown as number[][][]);
  }
  if (geometry.type === 'MultiPolygon') {
    return (geometry.coordinates as unknown as number[][][][])
      .some((poly) => pointInPolygon(lon, lat, poly));
  }
  return false;
}

/** Distance (m) to a Polygon OR MultiPolygon boundary; 0 if inside any part. */
export function distanceToGeometryMeters(lon: number, lat: number, geometry: Geometry): number {
  if (geometry.type === 'Polygon') {
    return distanceToRingsMeters(lon, lat, geometry.coordinates as unknown as number[][][]);
  }
  if (geometry.type === 'MultiPolygon') {
    return Math.min(
      ...(geometry.coordinates as unknown as number[][][][])
        .map((poly) => distanceToRingsMeters(lon, lat, poly)),
    );
  }
  return Infinity;
}

/** Back-compat alias — distance to a (Multi)Polygon boundary; 0 if inside. */
export function distanceToPolygonMeters(lon: number, lat: number, geometry: Geometry): number {
  return distanceToGeometryMeters(lon, lat, geometry);
}

function levelFor(inside: boolean, severity: string, distance: number, warningM: number): ProximityLevel {
  if (inside) return severity === 'blocking' ? 'breach' : 'entered';
  if (distance <= warningM) return 'warning';
  return 'clear';
}

function actionFor(level: ProximityLevel, category: string, distance: number): string {
  const label = category.replace(/_/g, ' ');
  if (level === 'breach') return `STOP — inside a no-work ${label}. Do not proceed; notify compliance immediately.`;
  if (level === 'entered') return `Inside ${label} — hold work and follow the buffer/habitat-window protocol.`;
  if (level === 'warning') return `Approaching ${label} (${Math.round(distance)} m) — slow down and confirm the boundary.`;
  return 'Clear of protected zones.';
}

/** On-device equivalent of `POST /api/geo/proximity`. */
export function evaluateProximity(
  lon: number, lat: number, zones: EnvironmentalConstraint[], warningMeters: number,
): ProximityResult {
  const out: ProximityZone[] = [];
  for (const z of zones) {
    if (!z.geometry) continue;
    const inside = pointInGeometry(lon, lat, z.geometry);
    const distance = inside ? 0 : Math.round(distanceToGeometryMeters(lon, lat, z.geometry) * 10) / 10;
    const level = levelFor(inside, z.severity, distance, warningMeters);
    out.push({
      id: z.id, name: z.name, category: z.category, severity: z.severity,
      distanceM: distance, inside, level, action: actionFor(level, z.category, distance),
    });
  }
  out.sort((a, b) => a.distanceM - b.distanceM);
  const overall = out.reduce<ProximityLevel>(
    (worst, z) => (RANK[z.level] > RANK[worst] ? z.level : worst), 'clear');
  const nearest = out[0] ?? null;
  return {
    lon, lat, warningMeters, overallLevel: overall,
    nearestName: nearest?.name ?? null,
    nearestDistanceM: nearest?.distanceM ?? null,
    zones: out,
    note: 'Computed on-device from cached zones (offline fallback).',
  };
}
