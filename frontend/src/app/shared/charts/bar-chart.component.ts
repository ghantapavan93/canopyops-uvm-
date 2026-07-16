import { Component, computed, input, output } from '@angular/core';

import { ChartSeries } from './line-chart.component';
import { toneVar } from './chart-colors';

export interface BarSegmentClick {
  category: string;
  series: string;
  value: number;
}

/** Stacked bar chart: one bar per category, stacked by series. Pure SVG.
 *  Emits (segmentClick) when a segment is clicked, for drill/filter. */
@Component({
  selector: 'app-bar-chart',
  standalone: true,
  template: `
    <div class="w-full">
      <svg viewBox="0 0 320 160" class="w-full" [style.height.px]="height()"
           role="img" [attr.aria-label]="ariaLabel()">
        @for (b of bars(); track b.cat) {
          @for (seg of b.segments; track seg.label) {
            <rect [attr.x]="b.x" [attr.y]="seg.y" [attr.width]="barW"
                  [attr.height]="seg.h" [attr.fill]="seg.color" rx="1.5"
                  style="cursor:pointer" class="transition-opacity hover:opacity-80"
                  (click)="segmentClick.emit({ category: b.cat, series: seg.label, value: seg.value })">
              <title>{{ b.cat }} · {{ seg.label }}: {{ seg.value }} — click to filter</title>
            </rect>
          }
          <text [attr.x]="b.x + barW / 2" y="154" text-anchor="middle" font-size="7"
                fill="var(--c-text-muted)">{{ b.cat }}</text>
        }
      </svg>
      <div class="mt-1 flex flex-wrap gap-x-4 gap-y-1">
        @for (s of series(); track s.label) {
          <span class="flex items-center gap-1.5 text-[11px] text-muted">
            <span class="inline-block h-2 w-2 rounded-sm" [style.background]="color(s.tone)"></span>
            {{ s.label }}
          </span>
        }
      </div>
    </div>
  `,
})
export class BarChartComponent {
  readonly series = input<ChartSeries[]>([]);
  readonly categories = input<string[]>([]);
  readonly height = input<number>(160);
  readonly segmentClick = output<BarSegmentClick>();

  private readonly top = 8;
  private readonly bottom = 20;
  readonly barW = 34;

  color = (t: string) => toneVar(t);
  ariaLabel = computed(() => `Stacked bar chart by ${this.categories().join(', ')}`);

  private totals = computed(() =>
    this.categories().map((_, ci) =>
      this.series().reduce((sum, s) => sum + (s.points[ci] ?? 0), 0),
    ),
  );

  readonly bars = computed(() => {
    const cats = this.categories();
    const max = Math.max(...this.totals(), 1);
    const plotH = 160 - this.top - this.bottom;
    // Keep a non-negative gap so a large category count can't drive bars off-canvas.
    const gap = Math.max(2, (320 - cats.length * this.barW) / (cats.length + 1));
    return cats.map((cat, ci) => {
      const x = gap + ci * (this.barW + gap);
      let cursor = 160 - this.bottom;
      const segments = this.series().map((s) => {
        const v = s.points[ci] ?? 0;
        const h = (v / max) * plotH;
        cursor -= h;
        return { label: s.label, value: v, color: toneVar(s.tone), y: cursor, h };
      });
      return { cat, x, segments };
    });
  });
}
