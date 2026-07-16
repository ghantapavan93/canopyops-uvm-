import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { ComplianceReport } from '../../core/models';
import { environment } from '../../../environments/environment';

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
  readonly error = signal<string | null>(null);
  readonly circuit = signal<string>('');           // '' = all circuits
  readonly circuits = signal<string[]>([]);
  readonly windowDays = signal<number>(0);         // 0 = all time

  readonly windows = [
    { label: 'All time', days: 0 },
    { label: '30 days', days: 30 },
    { label: '90 days', days: 90 },
    { label: '1 year', days: 365 },
  ];

  readonly levels = ['critical', 'high', 'elevated', 'low'] as const;
  readonly distTotal = computed(() =>
    Object.values(this.report()?.riskDistribution ?? {}).reduce((a, b) => a + b, 0) || 1);

  private sinceIso(): string | undefined {
    const d = this.windowDays();
    return d ? new Date(Date.now() - d * 864e5).toISOString() : undefined;
  }
  private query(): string {
    const p: string[] = [];
    if (this.circuit()) p.push(`circuit=${encodeURIComponent(this.circuit())}`);
    const s = this.sinceIso();
    if (s) p.push(`since=${encodeURIComponent(s)}`);
    return p.length ? '?' + p.join('&') : '';
  }
  /** Direct link to the server-generated PDF (honours circuit + date scope). */
  readonly pdfHref = computed(() => {
    this.circuit(); this.windowDays();     // track deps
    return `${environment.apiBase}/reports/compliance.pdf${this.query()}`;
  });

  constructor() { this.load(); }

  private load(): void {
    this.error.set(null);
    this.api.getComplianceReport(this.circuit() || undefined, this.sinceIso()).subscribe({
      next: (r) => {
        this.report.set(r);
        if (!this.circuit() && !this.windowDays() && !this.circuits().length) {
          this.circuits.set([...new Set(r.spans.map((s) => s.circuit))].sort());
        }
      },
      error: (err) =>
        this.error.set(err?.error?.message ?? 'Could not assemble the compliance report.'),
    });
  }
  setCircuit(c: string): void { this.circuit.set(c); this.load(); }
  setWindow(days: number): void { this.windowDays.set(days); this.load(); }

  print(): void { window.print(); }

  distPct(level: string): number {
    const r = this.report();
    return r ? Math.round(((r.riskDistribution[level] ?? 0) / this.distTotal()) * 100) : 0;
  }
  levelColor(level: string): string {
    return level === 'critical' || level === 'high' ? '#b4231f'
      : level === 'elevated' ? '#855c00' : '#0e6a39';
  }
}
