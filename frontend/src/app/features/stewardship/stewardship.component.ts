import { Component, computed, inject, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import { KpiTile, StewardshipPayload } from '../../core/models';
import { CONSTRAINT_META, TONE_CHIP } from '../../core/status';
import { DonutComponent, DonutSegment } from '../../shared/charts/donut.component';
import { GaugeComponent } from '../../shared/charts/gauge.component';
import { ChartSeries, LineChartComponent } from '../../shared/charts/line-chart.component';
import { SparklineComponent } from '../../shared/charts/sparkline.component';

@Component({
  selector: 'app-stewardship',
  standalone: true,
  imports: [SparklineComponent, LineChartComponent, GaugeComponent, DonutComponent],
  templateUrl: './stewardship.component.html',
})
export class StewardshipComponent {
  private api = inject(ApiService);
  readonly CONSTRAINT_META = CONSTRAINT_META;
  readonly TONE_CHIP = TONE_CHIP;

  readonly data = signal<StewardshipPayload | null>(null);
  readonly loading = signal(true);

  readonly methodDonut = computed<DonutSegment[]>(() =>
    (this.data()?.methodMix ?? []).map((s) => ({ label: s.label, value: s.points[0], tone: s.tone })),
  );
  readonly pollinatorSeries = computed<ChartSeries[]>(() =>
    this.data() ? [{ label: 'Pollinator habitat (acres)', tone: 'ok', points: this.data()!.pollinatorAcres }] : [],
  );

  constructor() {
    this.api.getStewardship().subscribe({
      next: (d) => { this.data.set(d); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  deltaTone(t: KpiTile): 'ok' | 'danger' | 'muted' {
    if (t.delta == null || t.delta === 0) return 'muted';
    return t.delta > 0 === t.deltaGood ? 'ok' : 'danger';
  }
  abs(n: number): number { return Math.abs(n); }
}
