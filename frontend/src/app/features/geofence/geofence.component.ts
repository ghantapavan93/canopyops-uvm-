import { Component, OnDestroy, computed, inject, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import { ConnectivityService } from '../../core/connectivity.service';
import { evaluateProximity } from '../../core/geofence';
import {
  Corridor, EnvironmentalConstraint, ProximityLevel, ProximityResult, ProximityZone,
} from '../../core/models';
import { ZoneCacheService } from '../../core/zone-cache.service';
import { GeofenceMapComponent } from './geofence-map.component';

interface AlertEvent {
  at: number;
  zone: string;
  level: ProximityLevel;
  distanceM: number;
}

const RANK: Record<ProximityLevel, number> = { clear: 0, warning: 1, entered: 2, breach: 3 };

// A synthetic patrol track that walks west→east straight into the seeded
// water-buffer zone, so the alert escalates clear → approaching → breach live.
const PATROL: [number, number][] = Array.from({ length: 22 }, (_, i) => {
  const t = i / 21;
  return [(-83.198 + t * 0.028), 40.112] as [number, number];
});

@Component({
  selector: 'app-geofence',
  standalone: true,
  imports: [GeofenceMapComponent],
  templateUrl: './geofence.component.html',
})
export class GeofenceComponent implements OnDestroy {
  private api = inject(ApiService);
  private zoneCache = inject(ZoneCacheService);
  conn = inject(ConnectivityService);

  readonly constraints = signal<EnvironmentalConstraint[]>([]);
  readonly corridors = signal<Corridor[]>([]);
  readonly position = signal<[number, number]>([-83.198, 40.112]);
  readonly warningMeters = signal(120);
  readonly result = signal<ProximityResult | null>(null);
  readonly log = signal<AlertEvent[]>([]);
  readonly patrolling = signal(false);

  // Where the last result was computed, plus the cached zone snapshot version —
  // this is what makes the offline story concrete and inspectable.
  readonly source = signal<'server' | 'on-device'>('server');
  readonly zoneVersion = signal<string>('');
  /** When online, whether the on-device engine agrees with the server. */
  readonly parity = signal<boolean | null>(null);
  private cachedZones: EnvironmentalConstraint[] = [];

  private prevLevels = new Map<string, ProximityLevel>();
  private patrolId: ReturnType<typeof setInterval> | null = null;
  private patrolStep = 0;
  private clock = 0;

  /** constraintId → current level, for the map colouring. */
  readonly levels = computed<Record<string, ProximityLevel>>(() => {
    const out: Record<string, ProximityLevel> = {};
    for (const z of this.result()?.zones ?? []) out[z.id] = z.level;
    return out;
  });
  readonly overall = computed<ProximityLevel>(() => this.result()?.overallLevel ?? 'clear');
  readonly zones = computed<ProximityZone[]>(() => this.result()?.zones ?? []);
  readonly nearest = computed<ProximityZone | null>(() => this.zones()[0] ?? null);

  readonly warningPresets = [60, 120, 200];

  constructor() {
    this.api.listCorridors().subscribe((c) => this.corridors.set(c));
    this.loadZones();
  }

  /** Load the protected-zone snapshot: show the cached copy instantly (works
   *  offline), then refresh from the server and re-cache when reachable. */
  private loadZones(): void {
    this.zoneCache.load().then((snap) => {
      if (snap && !this.cachedZones.length) {
        this.applyZones(snap.zones, snap.version);
        this.check();
      }
    });
    this.api.getZones().subscribe({
      next: (s) => {
        this.applyZones(s.zones, s.version);
        void this.zoneCache.save({ version: s.version, zones: s.zones, cachedAt: new Date().toISOString() });
        this.check();
      },
      error: () => this.check(),  // offline on first load → use whatever cache we have
    });
  }

  private applyZones(zones: EnvironmentalConstraint[], version: string): void {
    this.constraints.set(zones);
    this.cachedZones = zones;
    this.zoneVersion.set(version);
  }

  ngOnDestroy(): void {
    if (this.patrolId) clearInterval(this.patrolId);
  }

  onPositionChange(pos: [number, number]): void {
    this.stopPatrol();
    this.position.set(pos);
    this.check();
  }

  setWarning(m: number): void {
    this.warningMeters.set(m);
    this.check();
  }

  /** Geofence check: server-authoritative when online (with an on-device parity
   *  check), on-device from cached zones when offline or the API is unreachable. */
  private check(): void {
    const [lon, lat] = this.position();
    if (!this.conn.online()) { this.computeLocal(lon, lat); return; }
    this.api.proximity(lon, lat, this.warningMeters()).subscribe({
      next: (r) => {
        this.result.set(r);
        this.source.set('server');
        if (this.cachedZones.length) {
          const local = evaluateProximity(lon, lat, this.cachedZones, this.warningMeters());
          this.parity.set(local.overallLevel === r.overallLevel);
        }
        this.record(r);
      },
      error: () => this.computeLocal(lon, lat),
    });
  }

  /** On-device fallback using the cached zone snapshot — mirrors the server. */
  private computeLocal(lon: number, lat: number): void {
    const r = evaluateProximity(lon, lat, this.cachedZones, this.warningMeters());
    this.result.set(r);
    this.source.set('on-device');
    this.parity.set(null);
    this.record(r);
  }

  /** Demo control: flip connectivity to prove alerts survive going offline. */
  toggleOffline(): void {
    this.conn.setForced(!this.conn.online());
    this.check();
  }

  /** Append an alert-log entry whenever a zone escalates to a higher level. */
  private record(r: ProximityResult): void {
    const events: AlertEvent[] = [];
    for (const z of r.zones) {
      const prev = this.prevLevels.get(z.id) ?? 'clear';
      if (RANK[z.level] > RANK[prev] && z.level !== 'clear') {
        events.push({ at: this.clock++, zone: z.name, level: z.level, distanceM: z.distanceM });
      }
      this.prevLevels.set(z.id, z.level);
    }
    if (events.length) this.log.update((l) => [...events.reverse(), ...l].slice(0, 12));
  }

  // --- patrol simulation ---
  togglePatrol(): void {
    if (this.patrolling()) { this.stopPatrol(); return; }
    this.patrolling.set(true);
    this.patrolStep = 0;
    this.patrolId = setInterval(() => {
      if (this.patrolStep >= PATROL.length) { this.stopPatrol(); return; }
      this.position.set(PATROL[this.patrolStep++]);
      this.check();
    }, 550);
  }
  private stopPatrol(): void {
    this.patrolling.set(false);
    if (this.patrolId) { clearInterval(this.patrolId); this.patrolId = null; }
  }

  resetLog(): void {
    this.log.set([]);
    this.prevLevels.clear();
  }

  levelLabel(l: ProximityLevel): string {
    return l === 'breach' ? 'BREACH' : l === 'entered' ? 'INSIDE ZONE'
      : l === 'warning' ? 'APPROACHING' : 'CLEAR';
  }
  meters(v: number | null): string {
    if (v == null) return '—';
    return v >= 1000 ? `${(v / 1000).toFixed(1)} km` : `${Math.round(v)} m`;
  }
  barPct(z: ProximityZone): number {
    // Closeness bar: full when inside, tapering to 0 at ~3× the warning radius.
    const span = this.warningMeters() * 3;
    return Math.max(4, Math.round((1 - Math.min(1, z.distanceM / span)) * 100));
  }
}
