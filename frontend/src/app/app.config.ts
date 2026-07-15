import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, isDevMode, provideZoneChangeDetection } from '@angular/core';
import { provideRouter, withInMemoryScrolling } from '@angular/router';
import { provideServiceWorker } from '@angular/service-worker';

import { authInterceptor } from './core/auth.interceptor';
import { errorInterceptor } from './core/error.interceptor';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withInMemoryScrolling({ anchorScrolling: 'enabled' })),
    provideHttpClient(withInterceptors([authInterceptor, errorInterceptor])),
    // App shell + read-only API responses are cached by the service worker, so
    // the whole console (not just the geofence zones) survives going offline.
    // Skipped under Cypress (window.Cypress) — a controlling SW hangs e2e visits.
    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode() && !('Cypress' in window),
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
