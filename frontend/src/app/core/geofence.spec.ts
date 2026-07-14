import { EnvironmentalConstraint } from './models';
import {
  distanceToPolygonMeters, evaluateProximity, haversineMeters, pointInPolygon,
} from './geofence';

// A ~square zone around (-83.17, 40.112), matching the seeded water buffer box.
const box: number[][][] = [[
  [-83.18, 40.108], [-83.16, 40.108], [-83.16, 40.116], [-83.18, 40.116], [-83.18, 40.108],
]];

const zone = (over: Partial<EnvironmentalConstraint> = {}): EnvironmentalConstraint => ({
  id: 'z1', name: 'Water buffer', category: 'water_buffer', severity: 'blocking',
  geometry: { type: 'Polygon', coordinates: box }, ...over,
});

describe('geofence math', () => {
  it('detects a point inside the polygon', () => {
    expect(pointInPolygon(-83.17, 40.112, box)).toBe(true);
  });

  it('detects a point outside the polygon', () => {
    expect(pointInPolygon(-83.20, 40.112, box)).toBe(false);
  });

  it('returns 0 distance when inside, positive when outside', () => {
    const inside = distanceToPolygonMeters(-83.17, 40.112, { type: 'Polygon', coordinates: box } as any);
    const outside = distanceToPolygonMeters(-83.182, 40.112, { type: 'Polygon', coordinates: box } as any);
    expect(inside).toBe(0);
    expect(outside).toBeGreaterThan(0);
    expect(outside).toBeLessThan(400); // ~170 m west of the edge
  });

  it('measures a known east-west distance in metres', () => {
    // 0.001° lon at ~40° lat ≈ 85 m
    const d = haversineMeters(-83.18, 40.112, -83.181, 40.112);
    expect(d).toBeGreaterThan(70);
    expect(d).toBeLessThan(100);
  });
});

describe('evaluateProximity (offline fallback)', () => {
  it('flags a breach inside a blocking zone', () => {
    const r = evaluateProximity(-83.17, 40.112, [zone()], 60);
    expect(r.overallLevel).toBe('breach');
    expect(r.zones[0].inside).toBe(true);
    expect(r.zones[0].action).toContain('STOP');
  });

  it('warns when within the detection radius', () => {
    const r = evaluateProximity(-83.182, 40.112, [zone()], 300);
    expect(r.zones[0].inside).toBe(false);
    expect(r.overallLevel).toBe('warning');
  });

  it('is clear when far away', () => {
    const r = evaluateProximity(-83.0, 40.0, [zone()], 60);
    expect(r.overallLevel).toBe('clear');
  });

  it('treats an advisory zone as entered (not breach)', () => {
    const r = evaluateProximity(-83.17, 40.112, [zone({ severity: 'advisory' })], 60);
    expect(r.zones[0].level).toBe('entered');
  });
});
