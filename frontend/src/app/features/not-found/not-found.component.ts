import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { SwUpdate } from '@angular/service-worker';

/** Wildcard fallback. A route can be "missing" simply because the service worker
 *  is still serving a previously-cached shell that predates a new deploy — so
 *  before declaring a 404 we ask the SW to check for a newer version. If one is
 *  ready, the app root reloads into the fresh bundle (which knows the route); if
 *  not, we show a genuine not-found after a short grace window. */
@Component({
  selector: 'app-not-found',
  standalone: true,
  imports: [RouterLink],
  template: `
    <div class="grid h-full place-items-center bg-bg p-6 text-center">
      @if (state() === 'checking') {
        <div>
          <div class="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-border border-t-primary"></div>
          <p class="text-sm text-muted">Checking for the latest version…</p>
        </div>
      } @else {
        <div class="max-w-sm">
          <div class="text-5xl" aria-hidden="true">🧭</div>
          <h1 class="mt-3 text-lg font-semibold text-ink">Page not found</h1>
          <p class="mt-1 text-sm text-muted">That route doesn’t exist in this version of CanopyOps.</p>
          <a routerLink="/console/overview" class="mt-4 inline-block rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-ink no-underline">Go to the console →</a>
        </div>
      }
    </div>
  `,
})
export class NotFoundComponent {
  private updates = inject(SwUpdate);
  readonly state = signal<'checking' | 'notfound'>('checking');

  constructor() {
    if (this.updates.isEnabled) {
      // If a newer build exists, the app root's VERSION_READY handler reloads us
      // into it — this route may then resolve. Otherwise fall through to 404.
      this.updates.checkForUpdate().catch(() => {});
      setTimeout(() => this.state.set('notfound'), 3500);
    } else {
      this.state.set('notfound');
    }
  }
}
