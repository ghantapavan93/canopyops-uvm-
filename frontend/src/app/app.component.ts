import { Component, inject } from '@angular/core';
import { NavigationEnd, Router, RouterOutlet } from '@angular/router';
import { SwUpdate, VersionReadyEvent } from '@angular/service-worker';
import { filter } from 'rxjs/operators';

import { ToastService } from './core/toast.service';
import { ToastContainerComponent } from './shared/toast-container.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, ToastContainerComponent],
  template: `<router-outlet /><app-toast-container />`,
})
export class AppComponent {
  private updates = inject(SwUpdate);
  private router = inject(Router);
  private toast = inject(ToastService);
  private lastCheck = 0;

  constructor() {
    if (!this.updates.isEnabled) return;

    // When a new version has downloaded, tell the user and reload (safe — the
    // IndexedDB outbox persists across reloads).
    this.updates.versionUpdates
      .pipe(filter((e): e is VersionReadyEvent => e.type === 'VERSION_READY'))
      .subscribe(() => {
        this.toast.info('A new version is ready — updating…');
        setTimeout(() => document.location.reload(), 1200);
      });

    // Proactively poll for a newer build on load and on navigation (throttled),
    // so a fresh deploy is picked up promptly instead of serving a stale shell.
    this.check();
    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe(() => this.check());
  }

  private check(): void {
    const now = Date.now();
    if (now - this.lastCheck < 20000) return;
    this.lastCheck = now;
    this.updates.checkForUpdate().catch(() => {});
  }
}
