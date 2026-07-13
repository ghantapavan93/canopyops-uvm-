import {
  centeredCoverageBox,
  cornerFollowupBox,
  normalizeToSvg,
} from './geometry';
import { Geometry } from './models';

const UNIT: Geometry = {
  type: 'Polygon',
  coordinates: [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
};

function area(g: Geometry): number {
  const ring = g.coordinates[0] as number[][];
  let a = 0;
  for (let i = 0; i < ring.length - 1; i++) {
    a += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1];
  }
  return Math.abs(a) / 2;
}

describe('geometry coverage math', () => {
  it('centeredCoverageBox area equals the requested fraction', () => {
    // This is the guarantee behind the coverage slider: slider % = area %.
    for (const frac of [0.25, 0.36, 0.6, 1]) {
      expect(area(centeredCoverageBox(UNIT, frac))).toBeCloseTo(frac, 6);
    }
  });

  it('centeredCoverageBox stays centered on the planned polygon', () => {
    const box = centeredCoverageBox(UNIT, 0.36);
    const ring = box.coordinates[0] as number[][];
    const cx = (Math.min(...ring.map((p) => p[0])) + Math.max(...ring.map((p) => p[0]))) / 2;
    expect(cx).toBeCloseTo(0.5, 6);
  });

  it('centeredCoverageBox clamps out-of-range fractions', () => {
    expect(area(centeredCoverageBox(UNIT, 5))).toBeCloseTo(1, 6);
    expect(area(centeredCoverageBox(UNIT, -1))).toBeCloseTo(0, 6);
  });

  it('cornerFollowupBox anchors to the SW corner with the right area', () => {
    const box = cornerFollowupBox(UNIT, 0.25);
    expect(area(box)).toBeCloseTo(0.25, 6);
    expect(box.coordinates[0][0]).toEqual([0, 0]); // SW corner
  });

  it('normalizeToSvg maps the planned bounds into the 0..100 viewBox', () => {
    const pts = normalizeToSvg(UNIT, UNIT).split(' ');
    // minX,minY -> x=2, y=98 (y is flipped for SVG)
    expect(pts[0]).toBe('2,98');
    expect(normalizeToSvg(UNIT, null)).toBe('');
  });
});
