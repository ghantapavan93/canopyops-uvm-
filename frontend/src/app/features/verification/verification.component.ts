import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { PolygonDrawMapComponent } from '../../shared/charts/polygon-draw-map.component';
import {
  Geometry,
  ProofPack,
  TreatmentRecord,
  VerificationConclusion,
} from '../../core/models';
import { STATUS_META } from '../../core/status';
import { ToastService } from '../../core/toast.service';
import { StatusBadgeComponent } from '../../shared/status-badge.component';

const CONCLUSIONS: { value: VerificationConclusion; label: string }[] = [
  { value: 'effective', label: 'Effective' },
  { value: 'partially_effective', label: 'Partially effective' },
  { value: 'ineffective', label: 'Ineffective' },
  { value: 'inconclusive', label: 'Inconclusive' },
];

@Component({
  selector: 'app-verification',
  standalone: true,
  imports: [FormsModule, RouterLink, DatePipe, StatusBadgeComponent, PolygonDrawMapComponent],
  templateUrl: './verification.component.html',
})
export class VerificationComponent {
  private api = inject(ApiService);
  private auth = inject(AuthService);
  private toast = inject(ToastService);

  readonly STATUS_META = STATUS_META;
  readonly conclusions = CONCLUSIONS;

  readonly records = signal<TreatmentRecord[]>([]);
  readonly selectedId = signal<string | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly proof = signal<ProofPack | null>(null);

  // form state
  readonly conclusion = signal<VerificationConclusion>('partially_effective');
  readonly condition = signal('');
  readonly regrowth = signal(false);
  readonly compatible = signal(false);
  /** Reviewer's free-drawn rework polygon (from the map). */
  readonly drawnFollowup = signal<Geometry | null>(null);

  readonly canReview = computed(() =>
    this.auth.can('quality_reviewer', 'compliance_reviewer'),
  );
  readonly selected = computed(
    () => this.records().find((r) => r.planId === this.selectedId()) ?? null,
  );
  readonly needsFollowup = computed(() => this.conclusion() !== 'effective');

  /** Targeted follow-up = only the area the reviewer drew (never a blind repeat). */
  readonly followupGeometry = computed<Geometry | null>(() =>
    this.needsFollowup() ? this.drawnFollowup() : null,
  );

  onFollowupGeometry(g: Geometry | null): void {
    this.drawnFollowup.set(g);
  }

  constructor() {
    this.load();
  }

  private load(): void {
    this.api.listTreatments().subscribe((rows) => {
      this.records.set(
        rows.filter((r) =>
          ['awaiting_verification', 'effective', 'partially_effective', 'ineffective', 'inconclusive', 'follow_up_planned'].includes(r.status),
        ),
      );
    });
  }

  choose(id: string): void {
    this.selectedId.set(id);
    this.error.set(null);
    this.proof.set(null);
    this.conclusion.set('partially_effective');
    this.condition.set('');
    this.regrowth.set(false);
    this.compatible.set(false);
    this.drawnFollowup.set(null);
  }

  submitVerify(): void {
    const plan = this.selected();
    if (!plan) return;
    this.busy.set(true);
    this.error.set(null);
    this.api
      .verify(plan.planId, {
        conclusion: this.conclusion(),
        condition: this.condition() || undefined,
        regrowthObserved: this.regrowth(),
        compatibleCover: this.compatible(),
        followupGeometry: this.followupGeometry(),
      })
      .subscribe({
        next: () => { this.busy.set(false); this.load(); this.toast.success('Outcome recorded.'); },
        error: (e) => {
          this.busy.set(false);
          const msg = e?.error?.detail?.message ?? e?.error?.message ?? 'Verification failed.';
          this.error.set(msg);
          this.toast.error(msg);
        },
      });
  }

  planFollowup(): void {
    const plan = this.selected();
    if (!plan) return;
    this.busy.set(true);
    this.api.planFollowup(plan.planId).subscribe({
      next: () => { this.busy.set(false); this.load(); },
      error: (e) => { this.busy.set(false); this.error.set(e?.error?.detail?.message ?? 'Failed.'); },
    });
  }

  close(): void {
    const plan = this.selected();
    if (!plan) return;
    this.busy.set(true);
    this.api.closePlan(plan.planId).subscribe({
      next: () => {
        this.busy.set(false);
        this.api.getProof(plan.planId).subscribe((p) => this.proof.set(p));
        this.load();
        this.toast.success('Record closed — Proof Pack assembled.');
      },
      error: (e) => {
        this.busy.set(false);
        const msg = e?.error?.detail?.message ?? 'Failed to close.';
        this.error.set(msg);
        this.toast.error(msg);
      },
    });
  }

  pct(v: number | null): string {
    return v === null ? '—' : `${Math.round(v * 100)}%`;
  }
}
