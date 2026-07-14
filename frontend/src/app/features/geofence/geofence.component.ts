import { Component, OnDestroy, computed, inject, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import { ConnectivityService } from '../../core/connectivity.service';
import {
  Corridor, EnvironmentalConstraint, ProximityLevel, ProximityResult, ProximityZone,
} from '../../core/models';
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
  conn = inject(ConnectivityService);

  readonly constraints = signal<EnvironmentalConstraint[]>([]);
  readonly corridors = signal<Corridor[]>([]);
  readonly position = signal<[number, number]>([-83.198, 40.112]);
  readonly warningMeters = signal(120);
  readonly result = signal<ProximityResult | null>(null);
  readonly log = signal<AlertEvent[]>([]);
  readonly patrolling = signal(false);

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
    this.api.listConstraints().subscribe((c) => this.constraints.set(c));
    this.api.listCorridors().subscribe((c) => this.corridors.set(c));
    this.check();
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

  /** Server-authoritative geofence check for the current position. */
  private check(): void {
    const [lon, lat] = this.position();
    this.api.proximity(lon, lat, this.warningMeters()).subscribe({
      next: (r) => { this.result.set(r); this.record(r); },
      error: () => {},
    });
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
