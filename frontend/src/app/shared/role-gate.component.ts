import { Component, computed, inject, input, signal } from '@angular/core';

import { AuthService } from '../core/auth.service';
import { DEMO_PASSWORD, ROLE_LABEL, demoUserForRole } from '../core/demo-users';
import { Role } from '../core/models';

/** Explains a role-gated workspace and switches you into it in one click.
 *
 *  The RBAC was always correct — but a correct permission boundary that renders
 *  a blank screen is indistinguishable from an unfinished feature. A reviewer
 *  opening Field Execution as a Manager saw emptiness and concluded the module
 *  wasn't built; it was built, and it was refusing them on purpose. So say so,
 *  and offer the way forward here rather than making them hunt for the switcher.
 */
@Component({
  selector: 'app-role-gate',
  standalone: true,
  template: `
    <div class="rounded-lg border border-primary/40 bg-primary-soft p-5 text-center">
      <div class="mx-auto mb-2 grid h-10 w-10 place-items-center rounded-full bg-primary/15 text-lg"
           aria-hidden="true">🔒</div>
      <h2 class="text-base font-semibold text-ink">
        {{ workspace() }} is for {{ roleNames() }}
      </h2>
      <p class="mx-auto mt-1 max-w-md text-sm text-muted">
        {{ reason() || 'The server enforces this too — the button below signs you in as a different synthetic user, it does not bypass the check.' }}
      </p>

      <div class="mt-4 flex flex-wrap items-center justify-center gap-2">
        @for (r of switchable(); track r.role) {
          <button type="button" (click)="switchTo(r.role)" [disabled]="busy()"
                  class="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-ink hover:opacity-90 disabled:opacity-60">
            {{ busy() ? 'Switching…' : 'Switch to ' + r.label + ' and continue →' }}
          </button>
        }
      </div>

      @if (error(); as e) {
        <p class="mt-3 text-xs text-danger">{{ e }}</p>
      }
      <p class="mt-3 text-[11px] text-muted">
        Acting as {{ currentLabel() }} · synthetic demonstration sign-in
      </p>
    </div>
  `,
})
export class RoleGateComponent {
  private auth = inject(AuthService);

  /** Roles allowed to use this workspace. */
  readonly roles = input.required<Role[]>();
  /** The workspace name, e.g. "Field Execution". */
  readonly workspace = input.required<string>();
  /** Optional: why this boundary exists, in domain terms. */
  readonly reason = input<string>('');

  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  readonly roleNames = computed(() =>
    this.roles().map((r) => ROLE_LABEL[r]).join(' or '),
  );

  /** Only offer roles we actually have a synthetic sign-in for. */
  readonly switchable = computed(() =>
    this.roles()
      .map((role) => ({ role, label: demoUserForRole(role)?.label }))
      .filter((r): r is { role: Role; label: string } => !!r.label),
  );

  readonly currentLabel = computed(() => {
    const r = this.auth.role();
    return r ? ROLE_LABEL[r] : 'a signed-out visitor';
  });

  async switchTo(role: Role): Promise<void> {
    const user = demoUserForRole(role);
    if (!user) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.auth.login(user.email, DEMO_PASSWORD);
    } catch {
      this.error.set('Could not switch role — the API may be unreachable.');
    } finally {
      this.busy.set(false);
    }
  }
}
