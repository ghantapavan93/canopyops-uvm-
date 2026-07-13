import { Geometry } from './models';

interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export function polygonBounds(geometry: Geometry): Bounds {
  const ring = geometry.coordinates[0] as number[][];
  const xs = ring.map((p) => p[0]);
  const ys = ring.map((p) => p[1]);
  return {
    minX: Math.min(...xs),
    minY: Math.min(...ys),
    maxX: Math.max(...xs),
    maxY: Math.max(...ys),
  };
}

/** A centered box covering `areaFraction` (0..1) of the planned polygon's
 *  bounding box. Because each side scales by sqrt(fraction), the resulting
 *  AREA fraction equals `areaFraction` — so the coverage slider reads as % area. */
export function centeredCoverageBox(planned: Geometry, areaFraction: number): Geometry {
  const { minX, minY, maxX, maxY } = polygonBounds(planned);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const s = Math.sqrt(Math.max(0, Math.min(1, areaFraction)));
  const w = ((maxX - minX) / 2) * s;
  const h = ((maxY - minY) / 2) * s;
  return {
    type: 'Polygon',
    coordinates: [[[cx - w, cy - h], [cx + w, cy - h], [cx + w, cy + h], [cx - w, cy + h], [cx - w, cy - h]]],
  };
}

/** A follow-up box anchored to the SW corner covering `areaFraction` of the
 *  planned bounds — "only the area needing another pass." */
export function cornerFollowupBox(planned: Geometry, areaFraction: number): Geometry {
  const { minX, minY, maxX, maxY } = polygonBounds(planned);
  const s = Math.sqrt(Math.max(0, Math.min(1, areaFraction)));
  const w = (maxX - minX) * s;
  const h = (maxY - minY) * s;
  return {
    type: 'Polygon',
    coordinates: [[[minX, minY], [minX + w, minY], [minX + w, minY + h], [minX, minY + h], [minX, minY]]],
  };
}

/** Normalize a polygon's ring into an SVG points string within a 0..100 box. */
export function normalizeToSvg(planned: Geometry, geometry: Geometry | null): string {
  if (!geometry) return '';
  const { minX, minY, maxX, maxY } = polygonBounds(planned);
  return (geometry.coordinates[0] as number[][])
    .map(
      ([x, y]) =>
        `${((x - minX) / (maxX - minX)) * 96 + 2},${98 - ((y - minY) / (maxY - minY)) * 96}`,
    )
    .join(' ');
}
