import { NgClass } from '@angular/common';
import { Component, HostListener, OnDestroy, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { BarChartComponent, BarSegmentClick } from '../../shared/charts/bar-chart.component';
import { ApiService } from '../../core/api.service';
import {
  ActivityItem, EncroachmentMap, KpiTile, MetricSource, OverviewPayload, RegionCell,
  StatusCount, TreatmentStatus,
} from '../../core/models';
import { STATUS_META, Tone } from '../../core/status';
import { ChoroplethMapComponent } from '../../shared/charts/choropleth-map.component';
import { DonutComponent, DonutSegment } from '../../shared/charts/donut.component';
import { GaugeComponent } from '../../shared/charts/gauge.component';
import { ChartSeries, LineChartComponent } from '../../shared/charts/line-chart.component';
import { SparklineComponent } from '../../shared/charts/sparkline.component';
import { ReliabilityOutcomeComponent } from './reliability-outcome.component';

/** One segment of the live lifecycle bar. */
export interface LifecycleSeg {
  status: TreatmentStatus;
  label: string;
  glyph: string;
  tone: Tone;
  count: number;
  pct: number;
}

interface DrillMeta {
  definition: string;
  benchmark: string;
  context: 'cycle' | 'hftd' | 'quality' | 'cost' | 'none';
  link?: { route: string; label: string; query?: Record<string, string> };
}

const DRILL: Record<string, DrillMeta> = {
  attainment: {
    definition: 'Completed spans ÷ the annual planned work. NERC FAC-003 requires 100% of the transmission plan to be worked each year.',
    benchmark: 'Regulatory target: 100% of annual plan',
    context: 'cycle',
    link: { route: '/console/command', label: 'Open the work queue' },
  },
  mvcd: {
    definition: 'Share of spans clear of the Minimum Vegetation Clearance Distance. In HFTD areas the standard is 4 ft year-round / 12 ft at time of prune.',
    benchmark: 'Higher is better — non-compliance is a reportable event',
    context: 'hftd',
    link: { route: '/console/command', label: 'Review flagged spans', query: { attention: '1' } },
  },
  hftd: {
    definition: 'Work-plan completion weighted by wildfire ignition risk (High Fire-Threat District tiers). Tier 3 (extreme) is prioritized first.',
    benchmark: 'Risk-weighted — extreme tiers carry the most weight',
    context: 'hftd',
    link: { route: '/console/command', label: 'View HFTD work', query: { priority: 'hazard' } },
  },
  saidi: {
    definition: 'Tree-caused System Average Interruption Duration Index — outage minutes attributable to vegetation. ~85% of tree outages originate off-ROW.',
    benchmark: 'Lower is better — trending down',
    context: 'none',
  },
  evidence: {
    definition: 'Share of records with a complete, audit-ready evidence set. A failed upload keeps a record incomplete and blocks outcome verification.',
    benchmark: 'Computed from live records — recover failed uploads to raise it',
    context: 'quality',
    link: { route: '/console/sync', label: 'Recover failed uploads' },
  },
  spend: {
    definition: 'Year-to-date spend against budget. Cost per span is an internal trend only — a poor cross-utility benchmark (T&D World).',
    benchmark: 'Manage to budget — not a cross-utility scorecard',
    context: 'cost',
  },
};

/** How each metric's provenance is shown. The dashboard blends numbers computed
 *  from the live records with illustrative program-scale trends — labelling that
 *  is the difference between a demo a reviewer can trust and one they can't. */
const SOURCE_META: Record<MetricSource, { label: string; chip: string; title: string }> = {
  live: {
    label: 'LIVE',
    chip: 'bg-ok-soft text-ok',
    title: 'Computed from the records in this demo database.',
  },
  blended: {
    label: 'LIVE VALUE · ILLUSTRATIVE TREND',
    chip: 'bg-info-soft text-info',
    title: 'The number is computed from the live records; the trend line beneath it is an illustrative program-scale series, not history.',
  },
  synthetic: {
    label: 'ILLUSTRATIVE',
    chip: 'bg-warn-soft text-warn',
    title: 'A synthetic program-scale figure. Nothing in this prototype computes it — it shows the shape a real programme would report.',
  },
};

@Component({
  selector: 'app-overview',
  standalone: true,
  imports: [
    RouterLink, SparklineComponent, LineChartComponent, BarChartComponent, GaugeComponent,
    DonutComponent, ChoroplethMapComponent, ReliabilityOutcomeComponent, NgClass,
  ],
  templateUrl: './overview.component.html',
})
export class OverviewComponent implements OnDestroy {
  private api = inject(ApiService);
  private router = inject(Router);
  readonly SOURCE_META = SOURCE_META;
  readonly data = signal<OverviewPayload | null>(null);
  readonly loading = signal(true);
  readonly refreshing = signal(false);
  readonly encroach = signal<EncroachmentMap | null>(null);
  readonly topRegions = computed(() =>
    [...(this.encroach()?.regions ?? [])].sort((a, b) => b.encroachments - a.encroachments),
  );

  private readonly RAMP = ['#fde5e3', '#f6b0ab', '#e97b73', '#d1453f', '#a11f1a'];
  regionColor(r: RegionCell): string {
    const max = this.encroach()?.maxEncroachments || 1;
    return this.RAMP[Math.min(4, Math.floor((r.encroachments / max) * 5))];
  }

  onRegionClick(r: RegionCell): void {
    this.router.navigate(['/console/command'], { queryParams: { q: r.circuit } });
  }

  // --- period selector ---
  readonly periods = [
    { key: 'ytd', label: 'YTD' },
    { key: 'quarter', label: 'Quarter' },
    { key: 'cycle', label: 'Cycle' },
  ];
  readonly period = signal('ytd');

  setPeriod(key: string): void {
    if (this.period() === key) return;
    this.period.set(key);
    this.load(key);
  }

  private load(period: string, silent = false): void {
    if (silent) this.refreshing.set(true);
    else this.loading.set(true);
    this.api.getOverview(period).subscribe({
      next: (d) => {
        this.data.set(d);
        this.loading.set(false);
        this.refreshing.set(false);
        this.lastSync.set(this.tick());
      },
      error: () => { this.loading.set(false); this.refreshing.set(false); },
    });
  }

  // --- live refresh: the overview reflects real DB state, so it polls the API
  // and re-reads the audit trail + lifecycle counts. Fully client-controlled.
  readonly live = signal(true);
  readonly lastSync = signal(0);
  private readonly tick = signal(0);        // seconds since the epoch of this session
  private clockId: ReturnType<typeof setInterval> | null = null;
  private pollId: ReturnType<typeof setInterval> | null = null;
  private readonly start = Date.now();

  /** Whole seconds since the last successful fetch — drives "updated Ns ago". */
  readonly agoSeconds = computed(() => Math.max(0, this.tick() - this.lastSync()));

  refreshNow(): void {
    this.load(this.period(), true);
  }

  toggleLive(): void {
    const on = !this.live();
    this.live.set(on);
    if (on) this.startPoll();
    else if (this.pollId) { clearInterval(this.pollId); this.pollId = null; }
  }

  private startPoll(): void {
    if (this.pollId) clearInterval(this.pollId);
    this.pollId = setInterval(() => {
      if (this.live() && !document.hidden) this.load(this.period(), true);
    }, 12000);
  }

  ngOnDestroy(): void {
    if (this.clockId) clearInterval(this.clockId);
    if (this.pollId) clearInterval(this.pollId);
  }

  // --- REAL lifecycle distribution (one SQL GROUP BY server-side) ---
  readonly lifecycle = computed<LifecycleSeg[]>(() => {
    const dist = this.data()?.statusDistribution ?? [];
    const total = dist.reduce((s, r) => s + r.count, 0) || 1;
    return dist.map((r: StatusCount) => {
      const meta = STATUS_META[r.status];
      return {
        status: r.status, label: meta.label, glyph: meta.glyph, tone: meta.tone,
        count: r.count, pct: (r.count / total) * 100,
      };
    });
  });
  readonly lifecycleTotal = computed(() =>
    (this.data()?.statusDistribution ?? []).reduce((s, r) => s + r.count, 0));

  onStatusClick(seg: LifecycleSeg): void {
    this.router.navigate(['/console/command'], { queryParams: { status: seg.status } });
  }

  // --- REAL recent activity (immutable audit trail, newest first) ---
  readonly activity = computed<ActivityItem[]>(() => this.data()?.recentActivity ?? []);

  /** Human phrasing for an audit action key like "plan.approved". */
  actionLabel(action: string): string {
    const map: Record<string, string> = {
      'plan.created': 'Plan created',
      'plan.approved': 'Plan approved',
      'plan.revised': 'Plan revised',
      'execution.recorded': 'Field execution recorded',
      'execution.synced': 'Execution synced',
      'verification.recorded': 'Outcome verified',
      'plan.closed': 'Record closed with proof',
      'conflict.resolved': 'Conflict resolved',
    };
    return map[action] ?? action.replace(/[._]/g, ' ');
  }

  /** Relative "3m ago" style, recomputed each clock tick. */
  ago(iso: string): string {
    this.tick();  // subscribe to the ticking clock
    const secs = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
    if (secs < 60) return `${secs}s ago`;
    const mins = Math.round(secs / 60);
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.round(hrs / 24)}d ago`;
  }

  /** Bar-segment click → filter the Command Center by the mapped priority. */
  onSegment(seg: BarSegmentClick): void {
    const map: Record<string, string> = {
      'Hazard / target trees': 'hazard',
      'Mid-cycle / hot-spot': 'elevated',
      'Cycle prune': 'routine',
      'Remaining': 'hazard',
    };
    const priority = map[seg.series];
    this.router.navigate(['/console/command'], {
      queryParams: priority ? { priority } : {},
    });
  }

  // --- drill-down drawer ---
  readonly selectedTile = signal<KpiTile | null>(null);
  readonly drill = computed<DrillMeta | null>(() => {
    const t = this.selectedTile();
    return t ? DRILL[t.key] ?? null : null;
  });
  readonly drillSeries = computed<ChartSeries[]>(() => {
    const t = this.selectedTile();
    return t ? [{ label: t.label, tone: t.tone, points: t.spark }] : [];
  });

  openTile(t: KpiTile): void {
    this.selectedTile.set(t);
  }
  closeTile(): void {
    this.selectedTile.set(null);
  }
  @HostListener('document:keydown.escape')
  onEsc(): void {
    this.closeTile();
  }

  readonly attainmentSeries = computed<ChartSeries[]>(() => {
    const d = this.data();
    return d ? [
      { label: 'Planned spans', tone: 'neutral', points: d.plannedSpans },
      { label: 'Completed spans', tone: 'primary', points: d.completedSpans },
    ] : [];
  });

  readonly saidiSeries = computed<ChartSeries[]>(() =>
    this.data() ? [{ label: 'Tree-caused SAIDI (min)', tone: 'info', points: this.data()!.saidiPoints }] : []);

  readonly regrowthSeries = computed<ChartSeries[]>(() =>
    this.data() ? [{ label: 'Regrowth / re-treatment %', tone: 'warn', points: this.data()!.regrowthPoints }] : []);

  readonly costSeries = computed<ChartSeries[]>(() =>
    this.data() ? [{ label: 'Cost per span ($)', tone: 'neutral', points: this.data()!.costPerSpan }] : []);

  readonly prodSeries = computed<ChartSeries[]>(() =>
    this.data() ? [{ label: 'Man-hours per span', tone: 'primary', points: this.data()!.productionRate }] : []);

  readonly qualityDonut = computed<DonutSegment[]>(() =>
    (this.data()?.qualityBreakdown ?? []).map((s) => ({ label: s.label, value: s.points[0], tone: s.tone })));

  constructor() {
    this.tick.set(Math.floor((Date.now() - this.start) / 1000));
    this.load('ytd');
    this.api.getEncroachments().subscribe((e) => this.encroach.set(e));
    // 1s clock drives relative timestamps + "updated Ns ago" without refetching.
    this.clockId = setInterval(
      () => this.tick.set(Math.floor((Date.now() - this.start) / 1000)),
      1000,
    );
    this.startPoll();
  }

  abs(n: number): number {
    return Math.abs(n);
  }

  /** Tone for a delta chip given whether an increase is good. */
  deltaTone(t: KpiTile): 'ok' | 'danger' | 'muted' {
    if (t.delta == null || t.delta === 0) return 'muted';
    const up = t.delta > 0;
    return up === t.deltaGood ? 'ok' : 'danger';
  }
}
