import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { ToastService } from './toast.service';

// Debounce identical error toasts so a burst of failures doesn't spam the UI.
let lastToast = '';
let lastAt = 0;

/** Surface unexpected API failures (server errors + lost connectivity) as a
 *  toast, so nothing fails silently. Errors the app resolves itself — auth
 *  (401) and offline sync conflicts (409) — are left for their own handlers. */
export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const toast = inject(ToastService);
  return next(req).pipe(
    catchError((err: HttpErrorResponse) => {
      const handled = err.status === 401 || err.status === 409;
      const isServerOrNetwork = err.status === 0 || err.status >= 500;
      if (!handled && isServerOrNetwork) {
        const msg = err.status === 0
          ? 'Network unavailable — the API could not be reached.'
          : (err.error?.message ?? `Server error (${err.status}) on ${req.method} ${req.url}`);
        const now = Date.now();
        if (msg !== lastToast || now - lastAt > 4000) {
          toast.error(msg);
          lastToast = msg;
          lastAt = now;
        }
      }
      return throwError(() => err);
    }),
  );
};
