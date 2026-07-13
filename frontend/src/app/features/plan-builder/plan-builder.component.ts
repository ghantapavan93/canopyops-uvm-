import { DatePipe } from '@angular/common';
import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import {
  Corridor,
  EvidenceType,
  GeoAnalyze,
  Geometry,
  MethodCategory,
  TreatmentRecord,
} from '../../core/models';
import { CONSTRAINT_META, PRIORITY_META } from '../../core/status';
import { ToastService } from '../../core/toast.service';
import { PolygonDrawMapComponent } from '../../shared/charts/polygon-draw-map.component';

const METHODS: MethodCategory[] = ['manual', 'mechanical', 'herbicide', 'biological', 'cultural'];
const EVIDENCE: EvidenceType[] = ['photo_before', 'photo_after', 'clearance_measurement', 'note', 'form'];

@Component({
  selector: 'app-plan-builder',
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, DatePipe, PolygonDrawMapComponent],
  templateUrl: './plan-builder.component.html',
})
export class PlanBuilderComponent {
  private api = inject(ApiService);
  private auth = inject(AuthService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);

  readonly methods = METHODS;
  readonly evidenceTypes = EVIDENCE;
  readonly CONSTRAINT_META = CONSTRAINT_META;
  readonly PRIORITY_META = PRIORITY_META;

  readonly corridors = signal<Corridor[]>([]);
  readonly geometry = signal<Geometry | null>(null);
  readonly analysis = signal<GeoAnalyze | null>(null);
  readonly ackBlocking = signal(false);
  readonly requiredEvidence = signal<Set<EvidenceType>>(
    new Set<EvidenceType>(['photo_before', 'photo_after', 'clearance_measurement']),
  );
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly created = signal<TreatmentRecord | null>(null);

  readonly canCreate = computed(() => this.auth.can('program_manager'));

  readonly form = this.fb.nonNullable.group({
    corridorId: ['', Validators.required],
    priority: ['routine', Validators.required],
    targetCondition: ['', [Validators.required, Validators.minLength(12)]],
    methodCategory: ['mechanical', Validators.required],
    verificationWindowDays: [30, [Validators.required, Validators.min(7), Validators.max(365)]],
    cycle: ['mid_cycle', Validators.required],
    dueInDays: [14, [Validators.required, Validators.min(1), Validators.max(180)]],
  });

  // Live mirror of the reactive form so computed previews/checklist react to
  // every keystroke and control change.
  readonly formValue = toSignal(this.form.valueChanges, { initialValue: this.form.getRawValue() });

  readonly selectedCorridor = computed(
    () => this.corridors().find((c) => c.id === this.formValue().corridorId) ?? null,
  );

  readonly ready = computed(
    () =>
      this.form.valid &&
      this.geometry() !== null &&
      this.requiredEvidence().size > 0 &&
      this.canCreate() &&
      // A blocking constraint intersection must be explicitly acknowledged.
      (!this.analysis()?.blocking || this.ackBlocking()),
  );

  /** Live readiness checklist — each item ticks as the requirement is met. */
  readonly checklist = computed(() => {
    const fv = this.formValue();
    const a = this.analysis();
    const items = [
      { label: 'Corridor selected', done: !!fv.corridorId },
      { label: 'Treatment area drawn', done: this.geometry() !== null },
      { label: 'Target outcome described (12+ chars)', done: this.form.controls.targetCondition.valid },
      { label: 'At least one evidence type', done: this.requiredEvidence().size > 0 },
      { label: 'Verification window valid', done: this.form.controls.verificationWindowDays.valid && this.form.controls.dueInDays.valid },
    ];
    if (a?.blocking) items.push({ label: 'Blocking constraint acknowledged', done: this.ackBlocking() });
    return items;
  });

  readonly remaining = computed(() => this.checklist().filter((i) => !i.done).length);

  private readonly today = new Date();
  private addDays(base: Date, days: number): Date {
    const d = new Date(base);
    d.setDate(d.getDate() + days);
    return d;
  }
  /** Field-work due date derived live from the "due in N days" input. */
  readonly dueDate = computed(() => this.addDays(this.today, this.formValue().dueInDays || 0));

  constructor() {
    this.api.listCorridors().subscribe((c) => this.corridors.set(c));
  }

  /** Ctrl/Cmd+Enter submits when the plan is ready — keyboard-first. */
  @HostListener('document:keydown', ['$event'])
  onKey(ev: KeyboardEvent): void {
    if ((ev.ctrlKey || ev.metaKey) && ev.key === 'Enter' && this.ready() && !this.busy()) {
      this.submit();
      ev.preventDefault();
    }
  }

  toggleEvidence(t: EvidenceType): void {
    this.requiredEvidence.update((s) => {
      const next = new Set(s);
      next.has(t) ? next.delete(t) : next.add(t);
      return next;
    });
  }

  onGeometry(g: Geometry | null): void {
    this.geometry.set(g);
    this.ackBlocking.set(false);
    if (g) {
      this.api.analyzeGeometry(g).subscribe({
        next: (a) => this.analysis.set(a),
        error: () => this.analysis.set(null),
      });
    } else {
      this.analysis.set(null);
    }
  }

  submit(): void {
    if (!this.ready()) return;
    this.busy.set(true);
    this.error.set(null);
    const v = this.form.getRawValue();
    this.api
      .createPlan({
        corridorId: v.corridorId,
        priority: v.priority as any,
        targetCondition: v.targetCondition,
        methodCategory: v.methodCategory as MethodCategory,
        requiredEvidence: [...this.requiredEvidence()],
        verificationWindowDays: v.verificationWindowDays,
        cycle: v.cycle,
        dueInDays: v.dueInDays,
        plannedGeometry: this.geometry()!,
      })
      .subscribe({
        next: (rec) => {
          this.busy.set(false);
          this.created.set(rec);
          this.toast.success(`Plan ${rec.workOrderRef} created and scheduled.`);
        },
        error: (e) => {
          this.busy.set(false);
          const msg = e?.error?.detail?.message ?? e?.error?.message ?? 'Could not create the plan.';
          this.error.set(msg);
          this.toast.error(msg);
        },
      });
  }

  startAnother(): void {
    this.created.set(null);
    this.geometry.set(null);
    this.analysis.set(null);
    this.ackBlocking.set(false);
    this.form.reset({
      corridorId: '', priority: 'routine', targetCondition: '', methodCategory: 'mechanical',
      verificationWindowDays: 30, cycle: 'mid_cycle', dueInDays: 14,
    });
  }
}
