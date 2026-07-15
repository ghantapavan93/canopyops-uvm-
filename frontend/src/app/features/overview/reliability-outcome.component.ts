import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { ReliabilityBoard, ReliabilityCircuit, ReliabilityClass } from '../../core/models';

/** Reliability outcome — the quantitative form of "closed ≠ effective".
 *  Pairs closed work with the reliability indices UVM is judged by
 *  (SAIDI/SAIFI/CAIDI/CMI). Movement is synthetic but driven by real record
 *  state, so a circuit that closed work with weak evidence / low coverage shows
 *  little or no SAIDI improvement — surfacing "closed, not effective". */
@Component({
  selector: 'app-reliability-outcome',
  standalone: true,
  imports: [RouterLink, DecimalPipe],
  template: `
    @if (board(); as b) {
      <section class="mb-4 rounded-lg border border-border bg-surface p-4">
        <header class="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 class="flex items-center gap-2 text-sm font-semibold text-ink">
              Reliability outcome
              <span class="rounded bg-primary-soft px-1.5 py-0.5 text-[10px] font-semibold text-primary">closed ≠ effective</span>
            </h2>
            <p class="text-[11px] text-muted">Did closed work actually move the indices UVM is judged by? Movement is synthetic but driven by real coverage, evidence &amp; verified status.</p>
          </div>
          <a routerLink="/console/verification" class="text-[11px] font-medium text-primary no-underline hover:underline">Open verification →</a>
        </header>

        <!-- program rollup -->
        <div class="grid grid-cols-2 gap-2 md:grid-cols-4">
          <div class="rounded-md bg-surface-2 p-2.5">
            <div class="text-[10px] uppercase tracking-wide text-muted">SAIDI (min/cust)</div>
            <div class="flex items-baseline gap-1.5">
              <span class="text-lg font-bold text-ink">{{ b.rollup.saidiAfter }}</span>
              <span class="text-[11px]" [class]="deltaClass(b.rollup.saidiDelta)">{{ deltaArrow(b.rollup.saidiDelta) }} {{ absDelta(b.rollup.saidiDelta) }}</span>
            </div>
            <div class="text-[10px] text-muted">was {{ b.rollup.saidiBefore }}</div>
          </div>
          <div class="rounded-md bg-surface-2 p-2.5">
            <div class="text-[10px] uppercase tracking-wide text-muted">SAIFI (int/cust)</div>
            <div class="flex items-baseline gap-1.5">
              <span class="text-lg font-bold text-ink">{{ b.rollup.saifiAfter }}</span>
              <span class="text-[11px]" [class]="deltaClass(b.rollup.saifiAfter - b.rollup.saifiBefore)">{{ deltaArrow(b.rollup.saifiAfter - b.rollup.saifiBefore) }}</span>
            </div>
            <div class="text-[10px] text-muted">was {{ b.rollup.saifiBefore }}</div>
          </div>
          <div class="rounded-md bg-surface-2 p-2.5">
            <div class="text-[10px] uppercase tracking-wide text-muted">Closed → effective</div>
            <div class="text-lg font-bold text-ink">{{ b.rollup.effectiveTotal }}<span class="text-[11px] font-normal text-muted"> / {{ b.rollup.closedTotal }}</span></div>
            <div class="text-[10px] text-muted">{{ b.rollup.customers | number }} customers</div>
          </div>
          <div class="rounded-md p-2.5" [class.bg-danger-soft]="b.rollup.closedNotEffectiveCircuits > 0" [class.bg-surface-2]="b.rollup.closedNotEffectiveCircuits === 0">
            <div class="text-[10px] uppercase tracking-wide text-muted">Closed, not effective</div>
            <div class="text-lg font-bold" [class.text-danger]="b.rollup.closedNotEffectiveCircuits > 0" [class.text-ink]="b.rollup.closedNotEffectiveCircuits === 0">{{ b.rollup.closedNotEffectiveCircuits }}</div>
            <div class="text-[10px] text-muted">circuit(s) need review</div>
          </div>
        </div>

        <!-- per-circuit: attention-first -->
        <div class="mt-3 overflow-x-auto">
          <table class="w-full text-xs">
            <thead>
              <tr class="text-left text-muted">
                <th class="py-1 pr-2 font-medium">Circuit</th>
                <th class="py-1 pr-2 text-right font-medium">Closed</th>
                <th class="py-1 pr-2 font-medium">Effectiveness</th>
                <th class="py-1 pr-2 font-medium">SAIDI (before → after)</th>
                <th class="py-1 pr-2 text-right font-medium">Δ</th>
                <th class="py-1 font-medium">Outcome</th>
              </tr>
            </thead>
            <tbody>
              @for (c of sorted(); track c.circuit) {
                <tr class="border-t border-border">
                  <td class="py-1.5 pr-2 font-mono font-semibold text-ink">{{ c.circuit }}</td>
                  <td class="py-1.5 pr-2 text-right">{{ c.closed }}</td>
                  <td class="py-1.5 pr-2">
                    <div class="flex items-center gap-1.5">
                      <div class="h-1.5 w-16 overflow-hidden rounded-full bg-surface-2">
                        <div class="h-full rounded-full" [style.width.%]="c.effectivenessPct" [style.background]="effColor(c)"></div>
                      </div>
                      <span class="text-[10px] text-muted">{{ c.effectivenessPct }}%</span>
                    </div>
                  </td>
                  <td class="py-1.5 pr-2 text-muted">{{ c.saidiBefore }} <span class="text-ink">→ {{ c.saidiAfter }}</span></td>
                  <td class="py-1.5 pr-2 text-right font-semibold" [class]="deltaClass(c.saidiDelta)">{{ deltaArrow(c.saidiDelta) }} {{ absDelta(c.saidiDelta) }}</td>
                  <td class="py-1.5">
                    <span class="rounded px-1.5 py-0.5 text-[10px] font-semibold" [class]="badgeClass(c.classification)">{{ label(c.classification) }}</span>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
        <p class="mt-2 text-[10px] text-muted">SAIDI/SAIFI/CAIDI/CMI are synthetic &amp; illustrative — but a circuit that closed work with weak evidence or low coverage shows little movement. {{ b.note }}</p>
      </section>
    }
  `,
})
export class ReliabilityOutcomeComponent {
  private api = inject(ApiService);
  readonly board = signal<ReliabilityBoard | null>(null);

  private readonly order: Record<ReliabilityClass, number> = {
    closed_not_effective: 0, mixed: 1, effective: 2, pending: 3,
  };
  readonly sorted = computed(() =>
    [...(this.board()?.circuits ?? [])].sort((a, b) => this.order[a.classification] - this.order[b.classification]));

  constructor() {
    this.api.getReliability().subscribe((b) => this.board.set(b));
  }

  // negative delta = fewer outage minutes = improvement (good, green)
  deltaClass(d: number): string {
    return d < -0.05 ? 'text-ok' : d > 0.05 ? 'text-danger' : 'text-muted';
  }
  deltaArrow(d: number): string {
    return d < -0.05 ? '▼' : d > 0.05 ? '▲' : '—';
  }
  absDelta(d: number): string {
    return Math.abs(d) < 0.05 ? '' : Math.abs(d).toFixed(1);
  }
  effColor(c: ReliabilityCircuit): string {
    return c.effectivenessPct >= 60 ? '#1f8a54' : c.effectivenessPct >= 30 ? '#a8720a' : '#b4231f';
  }
  badgeClass(k: ReliabilityClass): string {
    switch (k) {
      case 'effective': return 'bg-ok-soft text-ok';
      case 'closed_not_effective': return 'bg-danger-soft text-danger';
      case 'pending': return 'bg-surface-2 text-muted';
      default: return 'bg-info-soft text-info';
    }
  }
  label(k: ReliabilityClass): string {
    return k === 'closed_not_effective' ? 'closed, not effective'
      : k === 'effective' ? 'effective'
      : k === 'pending' ? 'no closed work' : 'improving';
  }
}
