import { Component, computed, input } from '@angular/core';

import { Meta, TONE_CHIP } from '../core/status';

/** Small status chip: glyph + label + tone. Meaning is carried by text and
 *  shape, not color alone. */
@Component({
  selector: 'app-status-badge',
  standalone: true,
  template: `
    <span
      class="inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-xs font-medium leading-none"
      [class]="chip()"
    >
      <span aria-hidden="true">{{ meta().glyph }}</span>
      <span>{{ meta().label }}</span>
    </span>
  `,
})
export class StatusBadgeComponent {
  readonly meta = input.required<Meta>();
  readonly chip = computed(() => TONE_CHIP[this.meta().tone]);
}
