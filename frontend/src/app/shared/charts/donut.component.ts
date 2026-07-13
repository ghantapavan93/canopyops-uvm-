import { Component, computed, input } from '@angular/core';

import { toneVar } from './chart-colors';

export interface DonutSegment {
  label: string;
  value: number;
  tone: string;
}

/** Donut chart with a centered total. Pure SVG. */
@Component({
  selector: 'app-donut',
  standalone: true,
  template: `
    <div class="flex items-center gap-4">
      <svg viewBox="0 0 100 100" [style.width.px]="size()" [style.height.px]="size()"
           role="img" [attr.aria-label]="ariaLabel()">
        @for (a of arcs(); track a.label) {
          <path [attr.d]="a.d" fill="none" [attr.stroke]="a.color" stroke-width="16">
            <title>{{ a.label }}: {{ a.value }}</title>
          </path>
        }
        <text x="50" y="48" text-anchor="middle" font-size="20" font-weight="700"
              fill="var(--c-text)">{{ total() }}</text>
        <text x="50" y="60" text-anchor="middle" font-size="7" fill="var(--c-text-muted)">
          {{ centerLabel() }}
        </text>
      </svg>
      <ul class="space-y-1">
        @for (s of segments(); track s.label) {
          <li class="flex items-center gap-2 text-xs">
            <span class="inline-block h-2.5 w-2.5 rounded-sm" [style.background]="color(s.tone)"></span>
            <span class="text-ink">{{ s.value }}</span>
            <span class="text-muted">{{ s.label }}</span>
          </li>
        }
      </ul>
    </div>
  `,
})
export class DonutComponent {
  readonly segments = input<DonutSegment[]>([]);
  readonly size = input<number>(120);
  readonly centerLabel = input<string>('total');

  color = (t: string) => toneVar(t);
  total = computed(() => this.segments().reduce((s, x) => s + x.value, 0));
  ariaLabel = computed(() => `Donut: ${this.segments().map((s) => `${s.label} ${s.value}`).join(', ')}`);

  private readonly r = 42;
  private readonly cx = 50;
  private readonly cy = 50;

  private pt(frac: number): [number, number] {
    const a = (frac * 360 - 90) * (Math.PI / 180);
    return [this.cx + this.r * Math.cos(a), this.cy + this.r * Math.sin(a)];
  }

  readonly arcs = computed(() => {
    const total = this.total() || 1;
    let acc = 0;
    return this.segments().map((s) => {
      const start = acc / total;
      acc += s.value;
      const end = acc / total;
      const [x1, y1] = this.pt(start);
      const [x2, y2] = this.pt(Math.max(end - 0.001, start));
      const large = end - start > 0.5 ? 1 : 0;
      return {
        label: s.label, value: s.value, color: toneVar(s.tone),
        d: `M${x1.toFixed(2)},${y1.toFixed(2)} A${this.r},${this.r} 0 ${large} 1 ${x2.toFixed(2)},${y2.toFixed(2)}`,
      };
    });
  });
}
