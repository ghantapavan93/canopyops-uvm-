import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { AuthService } from './auth.service';

/** Attaches the synthetic bearer token to same-origin API calls, and drops a
 *  session the server no longer accepts.
 *
 *  The app used to trust localStorage absolutely: if the stored token stopped
 *  being valid — expired overnight, or its user no longer existed after a demo
 *  reset — every request 401'd forever and the console just looked broken, with
 *  no way back short of devtools. A rejected token is now discarded on the spot,
 *  which returns the app to a working signed-out state (the public demo reads
 *  still render) and lets the role gates offer a fresh sign-in.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const token = auth.token;
  // Attach to API calls, but never to the login call itself (it mints the token).
  const isLogin = req.url.includes('/auth/token');
  if (token && req.url.includes('/api/') && !isLogin) {
    req = req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
  }
  return next(req).pipe(
    catchError((err: HttpErrorResponse) => {
      // Only for a token we actually sent — a 401 from the login endpoint means
      // bad credentials, not a stale session.
      if (err.status === 401 && token && !isLogin) {
        auth.logout();
      }
      return throwError(() => err);
    }),
  );
};
