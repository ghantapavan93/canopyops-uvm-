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
  readonly circuit = signal<string>('');           // '' = all circuits
  readonly circuits = signal<string[]>([]);

  readonly levels = ['critical', 'high', 'elevated', 'low'] as const;
  readonly distTotal = computed(() =>
    Object.values(this.report()?.riskDistribution ?? {}).reduce((a, b) => a + b, 0) || 1);
  /** Direct link to the server-generated PDF (honours the circuit scope). */
  readonly pdfHref = computed(() =>
    `${environment.apiBase}/reports/compliance.pdf${this.circuit() ? `?circuit=${this.circuit()}` : ''}`);

  constructor() { this.load(); }

  private load(): void {
    this.api.getComplianceReport(this.circuit() || undefined).subscribe((r) => {
      this.report.set(r);
      // Capture the full circuit list once (from the unscoped report).
      if (!this.circuit() && !this.circuits().length) {
        this.circuits.set([...new Set(r.spans.map((s) => s.circuit))].sort());
      }
    });
  }
  setCircuit(c: string): void { this.circuit.set(c); this.load(); }

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
