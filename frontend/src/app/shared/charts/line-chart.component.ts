import { Component, computed, input } from '@angular/core';

import { chartUid, toneVar } from './chart-colors';

export interface ChartSeries {
  label: string;
  tone: string;
  points: number[];
}

/** Responsive multi-series area/line chart with grid, y-ticks, x-labels, and a
 *  legend. Pure SVG + design-token colors (theme-aware). */
@Component({
  selector: 'app-line-chart',
  standalone: true,
  template: `
    <div class="w-full">
      <svg viewBox="0 0 320 160" class="w-full" [style.height.px]="height()"
           role="img" [attr.aria-label]="ariaLabel()">
        <!-- horizontal grid + y ticks -->
        @for (g of grid(); track g.y) {
          <line x1="34" [attr.y1]="g.y" x2="314" [attr.y2]="g.y"
                stroke="var(--c-border)" stroke-width="0.5" />
          <text x="30" [attr.y]="g.y + 3" text-anchor="end" font-size="7"
                fill="var(--c-text-muted)">{{ g.label }}</text>
        }
        <!-- x labels (sparse) -->
        @for (x of xLabels(); track x.i) {
          <text [attr.x]="x.x" y="156" text-anchor="middle" font-size="7"
                fill="var(--c-text-muted)">{{ x.label }}</text>
        }
        <!-- series -->
        @for (s of computedSeries(); track s.label) {
          @if (s.area) {
            <defs>
              <linearGradient [attr.id]="s.gid" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" [attr.stop-color]="s.color" stop-opacity="0.25" />
                <stop offset="100%" [attr.stop-color]="s.color" stop-opacity="0" />
              </linearGradient>
            </defs>
            <path [attr.d]="s.area" [attr.fill]="'url(#' + s.gid + ')'" />
          }
          <path [attr.d]="s.line" fill="none" [attr.stroke]="s.color" stroke-width="1.8"
                stroke-linejoin="round" stroke-linecap="round" />
        }
      </svg>
      @if (showLegend() && series().length > 1) {
        <div class="mt-1 flex flex-wrap gap-x-4 gap-y-1">
          @for (s of series(); track s.label) {
            <span class="flex items-center gap-1.5 text-[11px] text-muted">
              <span class="inline-block h-2 w-2 rounded-sm" [style.background]="color(s.tone)"></span>
              {{ s.label }}
            </span>
          }
        </div>
      }
    </div>
  `,
})
export class LineChartComponent {
  readonly series = input<ChartSeries[]>([]);
  readonly labels = input<string[]>([]);
  readonly height = input<number>(160);
  readonly suffix = input<string>('');
  readonly showLegend = input<boolean>(true);
  readonly fill = input<boolean>(true);

  private readonly padL = 34;
  private readonly padR = 6;
  private readonly padT = 8;
  private readonly padB = 16;

  color = (t: string) => toneVar(t);
  ariaLabel = computed(() => `Trend chart: ${this.series().map((s) => s.label).join(', ')}`);

  private bounds = computed(() => {
    const all = this.series().flatMap((s) => s.points);
    if (!all.length) return { min: 0, max: 1 };
    let min = Math.min(...all), max = Math.max(...all);
    if (min === max) { min -= 1; max += 1; }
    const pad = (max - min) * 0.12;
    return { min: min - pad, max: max + pad };
  });

  private x(i: number, n: number): number {
    return this.padL + (n <= 1 ? 0 : (i / (n - 1)) * (320 - this.padL - this.padR));
  }
  private y(v: number): number {
    const { min, max } = this.bounds();
    return this.padT + (1 - (v - min) / (max - min)) * (160 - this.padT - this.padB);
  }

  readonly grid = computed(() => {
    const { min, max } = this.bounds();
    return [0, 0.5, 1].map((t) => ({
      y: this.padT + t * (160 - this.padT - this.padB),
      label: (max - t * (max - min)).toFixed(0) + this.suffix(),
    }));
  });

  readonly xLabels = computed(() => {
    const l = this.labels();
    const step = Math.ceil(l.length / 6) || 1;
    return l.map((label, i) => ({ label, i, x: this.x(i, l.length) }))
      .filter((_, i) => i % step === 0);
  });

  readonly computedSeries = computed(() =>
    this.series().map((s) => {
      const n = s.points.length;
      const pts = s.points.map((v, i) => [this.x(i, n), this.y(v)] as [number, number]);
      const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
      const area = this.fill()
        ? `M${pts[0][0].toFixed(1)},${(160 - this.padB)} ` +
          pts.map((p) => `L${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ') +
          ` L${pts[n - 1][0].toFixed(1)},${(160 - this.padB)} Z`
        : '';
      return { label: s.label, color: toneVar(s.tone), line, area, gid: chartUid('lg') };
    }),
  );
}
