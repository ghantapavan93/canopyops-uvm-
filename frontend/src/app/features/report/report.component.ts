import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { ComplianceReport } from '../../core/models';

/** A print-ready compliance report — the exportable evidence artifact. Rendered
 *  as a standalone light document (no app chrome) so "Print / Save as PDF"
 *  produces a clean page. */
@Component({
  selector: 'app-report',
  standalone: true,
  imports: [RouterLink, DatePipe],
  templateUrl: './report.component.html',
  styleUrl: './report.component.scss',
})
export class ReportComponent {
  private api = inject(ApiService);
  readonly report = signal<ComplianceReport | null>(null);

  readonly levels = ['critical', 'high', 'elevated', 'low'] as const;
  readonly distTotal = computed(() =>
    Object.values(this.report()?.riskDistribution ?? {}).reduce((a, b) => a + b, 0) || 1);

  constructor() {
    this.api.getComplianceReport().subscribe((r) => this.report.set(r));
  }

  print(): void { window.print(); }

  distPct(level: string): number {
    const r = this.report();
    return r ? Math.round(((r.riskDistribution[level] ?? 0) / this.distTotal()) * 100) : 0;
  }
  levelColor(level: string): string {
    return level === 'critical' || level === 'high' ? '#b4231f'
      : level === 'elevated' ? '#a8720a' : '#1f8a54';
  }
}
