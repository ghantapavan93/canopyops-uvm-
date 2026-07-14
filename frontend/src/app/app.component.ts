import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
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
  private toast = inject(ToastService);

  constructor() {
    // When the service worker has fetched a new version, tell the user and
    // reload so they pick it up (safe: the outbox persists across reloads).
    if (this.updates.isEnabled) {
      this.updates.versionUpdates
        .pipe(filter((e): e is VersionReadyEvent => e.type === 'VERSION_READY'))
        .subscribe(() => {
          this.toast.info('A new version is ready — updating…');
          setTimeout(() => document.location.reload(), 1500);
        });
    }
  }
}
