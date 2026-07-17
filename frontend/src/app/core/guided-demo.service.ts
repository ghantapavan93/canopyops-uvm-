import { Injectable, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiService } from './api.service';
import { AuthService } from './auth.service';
import { ConnectivityService } from './connectivity.service';
import { DEMO_PASSWORD, demoUserForRole } from './demo-users';
import { centeredCoverageBox } from './geometry';
import { EvidenceInput, TreatmentRecord } from './models';
import { SyncService } from './sync.service';

/** Stages the four situations the Sync Center exists to explain.
 *
 *  Every one is PRODUCED, not faked. There are no hand-written outbox rows: the
 *  scenario signs in as the crew, really bumps a plan revision on the server,
 *  really goes offline, and really queues executions through the same code path
 *  the field UI uses. A reviewer who pokes at it finds a working system rather
 *  than a stage set — which is the entire point of the module.
 *
 *  It deliberately stops while OFFLINE and hands the last move to the reviewer:
 *  they flip connectivity On and watch the queue drain, recover, and surface a
 *  conflict. Being the one who presses the button is what makes it believable.
 */
@Injectable({ providedIn: 'root' })
export class GuidedDemoService {
  private api = inject(ApiService);
  private auth = inject(AuthService);
  private sync = inject(SyncService);
  private conn = inject(ConnectivityService);

  readonly running = signal(false);
  readonly error = signal<string | null>(null);
  /** What was staged, for the UI to explain after it runs. */
  readonly staged = signal<string[]>([]);

  async loadScenario(): Promise<void> {
    if (this.running()) return;
    this.running.set(true);
    this.error.set(null);
    this.staged.set([]);
    try {
      // The server gates recording to the crew/manager, so sign in as the crew
      // FIRST — otherwise every queued item just fails with a 401 and proves
      // nothing. Always mint a fresh token rather than trusting whatever is in
      // localStorage: a stored session can be stale (expired, or its user
      // replaced by a demo reset), and the scenario must not inherit that.
      const crew = demoUserForRole('field_crew');
      if (!crew) throw new Error('No synthetic field-crew sign-in is configured.');
      await this.auth.login(crew.email, DEMO_PASSWORD);

      const { items } = await firstValueFrom(
        this.api.listTreatments({
          status: ['draft', 'scheduled', 'in_progress', 'applied'],
          limit: 10,
        }),
      );
      const plans = items.filter((p) => p.plannedGeometry);
      if (plans.length < 2) {
        throw new Error('The demo data has no plans ready to record. Reset the demonstration first.');
      }

      const queued = plans[0];
      const conflicted = plans[1 % plans.length];
      const partial = plans[2 % plans.length];

      // Bump the plan revision BEFORE going offline — this is a real server call
      // standing in for "a manager edited the plan while the crew was out of
      // coverage". The crew's queued item then carries a stale revision.
      const staleRevision = conflicted.planRevision;
      await firstValueFrom(this.api.bumpPlanRevision(conflicted.planId));

      // Out of coverage. enqueue() only auto-sends when online, so from here the
      // items genuinely persist in IndexedDB instead of going straight out.
      this.conn.setForced(false);

      // 1 + 2) A queued execution, and a byte-for-byte replay of it under the
      // SAME idempotency key. On drain the server accepts the first and answers
      // `duplicate` to the second — a real de-duplication, not a label.
      const replayKey = crypto.randomUUID();
      await this.sync.enqueue(
        `${queued.workOrderRef} execution`,
        this.payload(queued, queued.planRevision, 0.92),
        replayKey,
      );
      await this.sync.enqueue(
        `${queued.workOrderRef} execution (retried after a dropped connection)`,
        this.payload(queued, queued.planRevision, 0.92),
        replayKey,
      );

      // 3) An execution whose after-photo will fail to upload — the record syncs
      // but its evidence stays incomplete and recoverable.
      await this.sync.enqueue(
        `${partial.workOrderRef} execution (photo upload will fail)`,
        this.payload(partial, partial.planRevision, 0.84, true),
      );

      // 4) The stale-revision execution → the server refuses it with a 409 and a
      // human decides, rather than silently overwriting the manager's edit.
      await this.sync.enqueue(
        `${conflicted.workOrderRef} execution (plan changed while offline)`,
        this.payload(conflicted, staleRevision, 0.88),
      );

      this.staged.set([
        `${queued.workOrderRef} — queued offline, plus a duplicate retry under the same key`,
        `${partial.workOrderRef} — a photo upload that will fail and can be recovered`,
        `${conflicted.workOrderRef} — the plan moved to revision ${staleRevision + 1} while offline`,
      ]);
    } catch (e) {
      const err = e as { error?: { message?: string }; message?: string };
      this.error.set(err?.error?.message ?? err?.message ?? 'Could not stage the scenario.');
      this.conn.followBrowser();
    } finally {
      this.running.set(false);
    }
  }

  private payload(
    plan: TreatmentRecord,
    revision: number,
    coverage: number,
    failPhoto = false,
  ) {
    const planned = plan.plannedGeometry;
    if (!planned) throw new Error(`${plan.workOrderRef} has no planned geometry to execute against.`);
    const evidence: EvidenceInput[] = [
      { type: 'photo_before', capturedAt: new Date().toISOString() },
      { type: 'photo_after', capturedAt: new Date().toISOString(), simulateUploadFailure: failPhoto },
      { type: 'clearance_measurement', capturedAt: new Date().toISOString() },
    ];
    return {
      planId: plan.planId,
      planRevision: revision,
      actualGeometry: centeredCoverageBox(planned, coverage),
      performedAt: new Date().toISOString(),
      constraintAcknowledged: true,
      evidence,
    };
  }
}
