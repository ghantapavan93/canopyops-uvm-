import { Component, computed, input } from '@angular/core';

import { chartUid, toneVar } from './chart-colors';

/** Tiny area sparkline for KPI tiles. Pure SVG, theme-aware. */
@Component({
  selector: 'app-sparkline',
  standalone: true,
  template: `
    <svg [attr.viewBox]="'0 0 100 ' + h" preserveAspectRatio="none"
         class="block w-full" [style.height.px]="h" aria-hidden="true">
      <defs>
        <linearGradient [attr.id]="gid" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" [attr.stop-color]="color()" stop-opacity="0.35" />
          <stop offset="100%" [attr.stop-color]="color()" stop-opacity="0" />
        </linearGradient>
      </defs>
      <path [attr.d]="area()" [attr.fill]="'url(#' + gid + ')'" />
      <path [attr.d]="line()" fill="none" [attr.stroke]="color()" stroke-width="1.6"
            stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke" />
    </svg>
  `,
})
export class SparklineComponent {
  readonly points = input<number[]>([]);
  readonly tone = input<string>('primary');
  readonly h = 28;
  readonly gid = chartUid('spark');

  readonly color = computed(() => toneVar(this.tone()));

  private coords = computed(() => {
    const p = this.points();
    if (p.length < 2) return [] as [number, number][];
    const min = Math.min(...p), max = Math.max(...p);
    const span = max - min || 1;
    return p.map((v, i) => [
      (i / (p.length - 1)) * 100,
      this.h - 3 - ((v - min) / span) * (this.h - 6),
    ] as [number, number]);
  });

  readonly line = computed(() =>
    this.coords().map((c, i) => `${i ? 'L' : 'M'}${c[0].toFixed(2)},${c[1].toFixed(2)}`).join(' '),
  );

  readonly area = computed(() => {
    const c = this.coords();
    if (!c.length) return '';
    return `M${c[0][0]},${this.h} ` +
      c.map((p) => `L${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(' ') +
      ` L${c[c.length - 1][0]},${this.h} Z`;
  });
}
