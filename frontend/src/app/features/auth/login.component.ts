import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth.service';

/** Synthetic sign-in. Real authorization is enforced by the API; this only
 *  obtains a token for a synthetic demo user. */
@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule, RouterLink],
  template: `
    <div class="grid min-h-screen place-items-center bg-bg px-6 text-ink">
      <div class="w-full max-w-sm rounded-lg border border-border bg-surface p-6 shadow-card">
        <a routerLink="/" class="mb-4 flex items-center gap-2 no-underline">
          <span class="grid h-8 w-8 place-items-center rounded-md bg-primary text-primary-ink" aria-hidden="true">❦</span>
          <span class="font-semibold text-ink">CanopyOps</span>
        </a>
        <h1 class="text-lg font-semibold">Sign in</h1>
        <p class="mt-1 text-xs text-muted">Synthetic demo accounts — password is <code>canopyops</code>.</p>

        <form (ngSubmit)="submit()" class="mt-4 space-y-3">
          <label class="block">
            <span class="text-xs font-medium text-muted">Email</span>
            <input name="email" [(ngModel)]="email" type="email" autocomplete="username"
              class="mt-1 w-full rounded-md border border-border bg-bg px-3 py-2 text-sm focus:border-primary" />
          </label>
          <label class="block">
            <span class="text-xs font-medium text-muted">Password</span>
            <input name="password" [(ngModel)]="password" type="password" autocomplete="current-password"
              class="mt-1 w-full rounded-md border border-border bg-bg px-3 py-2 text-sm focus:border-primary" />
          </label>
          @if (error()) {
            <p class="rounded-md bg-danger-soft px-2 py-1.5 text-xs text-danger">{{ error() }}</p>
          }
          <button type="submit" [disabled]="busy()"
            class="w-full rounded-md bg-primary py-2 text-sm font-semibold text-primary-ink hover:opacity-90 disabled:opacity-60">
            {{ busy() ? 'Signing in…' : 'Sign in' }}
          </button>
        </form>

        <div class="mt-4 grid grid-cols-2 gap-2 text-xs">
          @for (u of quick; track u.email) {
            <button (click)="fill(u.email)" class="rounded-md border border-border px-2 py-1 text-muted hover:bg-surface-2">
              {{ u.label }}
            </button>
          }
        </div>
      </div>
    </div>
  `,
})
export class LoginComponent {
  private auth = inject(AuthService);
  private router = inject(Router);

  email = 'manager@synthetic.test';
  password = 'canopyops';
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  readonly quick = [
    { label: 'Manager', email: 'manager@synthetic.test' },
    { label: 'Field crew', email: 'crew@synthetic.test' },
    { label: 'Reviewer', email: 'reviewer@synthetic.test' },
    { label: 'Compliance', email: 'compliance@synthetic.test' },
  ];

  fill(email: string): void {
    this.email = email;
  }

  async submit(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.auth.login(this.email, this.password);
      this.router.navigate(['/console/command']);
    } catch {
      this.error.set('Invalid credentials or API unavailable.');
    } finally {
      this.busy.set(false);
    }
  }
}
