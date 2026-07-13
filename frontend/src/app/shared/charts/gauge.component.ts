import { Component, computed, input } from '@angular/core';

import { toneVar } from './chart-colors';

/** Radial gauge (270° arc). Value 0..100. Pure SVG. */
@Component({
  selector: 'app-gauge',
  standalone: true,
  template: `
    <svg viewBox="0 0 100 82" class="w-full" [style.height.px]="height()"
         role="img" [attr.aria-label]="label() + ': ' + value() + '%'">
      <path [attr.d]="track" fill="none" stroke="var(--c-surface-2)"
            stroke-width="10" stroke-linecap="round" />
      <path [attr.d]="arc()" fill="none" [attr.stroke]="color()"
            stroke-width="10" stroke-linecap="round" />
      <text x="50" y="52" text-anchor="middle" font-size="22" font-weight="700"
            fill="var(--c-text)">{{ value() }}<tspan font-size="11">%</tspan></text>
      <text x="50" y="66" text-anchor="middle" font-size="8" fill="var(--c-text-muted)">
        {{ label() }}
      </text>
    </svg>
  `,
})
export class GaugeComponent {
  readonly value = input<number>(0);
  readonly label = input<string>('');
  readonly tone = input<string>('primary');
  readonly height = input<number>(96);

  // 270° arc from 135° to 405° (i.e. -225° sweep), center (50,50) r=40.
  private readonly cx = 50;
  private readonly cy = 50;
  private readonly r = 40;
  private readonly start = 135;
  private readonly sweep = 270;

  color = computed(() => toneVar(this.tone()));

  private pt(angleDeg: number): [number, number] {
    const a = (angleDeg * Math.PI) / 180;
    return [this.cx + this.r * Math.cos(a), this.cy + this.r * Math.sin(a)];
  }

  private arcPath(fromDeg: number, toDeg: number): string {
    const [x1, y1] = this.pt(fromDeg);
    const [x2, y2] = this.pt(toDeg);
    const large = toDeg - fromDeg > 180 ? 1 : 0;
    return `M${x1.toFixed(2)},${y1.toFixed(2)} A${this.r},${this.r} 0 ${large} 1 ${x2.toFixed(2)},${y2.toFixed(2)}`;
  }

  readonly track = this.arcPath(this.start, this.start + this.sweep);
  readonly arc = computed(() => {
    const v = Math.max(0, Math.min(100, this.value()));
    return this.arcPath(this.start, this.start + (this.sweep * v) / 100);
  });
}
