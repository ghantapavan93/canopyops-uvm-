import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import {
  AuditOutcome, AuditQueue, PlanDossier, QualityAuditRecord, VaultIndex,
} from '../../core/models';
import { ToastService } from '../../core/toast.service';

/** Quality & Compliance — the independent QA "checks and balances" audit of
 *  closed work, and the auto-assembled evidence vault (per-plan dossier mapped
 *  to NERC FAC-003 / TVMP / NESC / environmental requirements). */
@Component({
  selector: 'app-audit',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './audit.component.html',
})
export class AuditComponent {
  private api = inject(ApiService);
  private auth = inject(AuthService);
  private toast = inject(ToastService);

  readonly queue = signal<AuditQueue | null>(null);
  readonly vault = signal<VaultIndex | null>(null);

  readonly canAudit = computed(() => this.auth.can('quality_reviewer', 'compliance_reviewer'));

  readonly expandedAudit = signal<string | null>(null);
  readonly history = signal<QualityAuditRecord[]>([]);
  readonly note = signal('');
  readonly submitting = signal(false);

  readonly expandedVault = signal<string | null>(null);

  readonly outcomes: AuditOutcome[] = ['pass', 'conditional', 'fail'];

  constructor() { this.load(); }

  private load(): void {
    this.api.getAuditQueue().subscribe((q) => this.queue.set(q));
    this.api.getVault().subscribe((v) => this.vault.set(v));
  }

  toggleAudit(planId: string): void {
    if (this.expandedAudit() === planId) { this.expandedAudit.set(null); return; }
    this.expandedAudit.set(planId);
    this.note.set('');
    this.history.set([]);
    this.api.getAuditHistory(planId).subscribe((h) => this.history.set(h));
  }

  decide(planId: string, outcome: AuditOutcome): void {
    if (!this.canAudit() || this.submitting()) return;
    this.submitting.set(true);
    this.api.recordAudit(planId, outcome, this.note() || undefined).subscribe({
      next: () => {
        this.toast.success(`Audit recorded: ${outcome}`);
        this.submitting.set(false);
        this.note.set('');
        this.api.getAuditHistory(planId).subscribe((h) => this.history.set(h));
        this.load();   // queue + vault both reflect the new verdict (QA framework flips)
      },
      error: () => { this.toast.error?.('Could not record the audit'); this.submitting.set(false); },
    });
  }

  toggleVault(planId: string): void {
    this.expandedVault.set(this.expandedVault() === planId ? null : planId);
  }

  // --- presentation helpers ---
  outcomeClass(o: AuditOutcome | null): string {
    return o === 'pass' ? 'bg-ok-soft text-ok'
      : o === 'fail' ? 'bg-danger-soft text-danger'
      : o === 'conditional' ? 'bg-warn-soft text-warn' : 'bg-surface-2 text-muted';
  }
  scoreColor(score: number): string {
    return score >= 0.8 ? '#1f8a54' : score >= 0.5 ? '#a8720a' : '#b4231f';
  }
  completeColor(pct: number): string {
    return pct >= 80 ? '#1f8a54' : pct >= 50 ? '#a8720a' : '#b4231f';
  }
  dossier(planId: string): PlanDossier | undefined {
    return this.vault()?.plans.find((p) => p.planId === planId);
  }
}
