import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';

import { AuthService } from './auth.service';

/** Attaches the synthetic bearer token to same-origin API calls. */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const token = auth.token;
  // Attach to API calls, but never to the login call itself (it mints the token).
  if (token && req.url.includes('/api/') && !req.url.includes('/auth/token')) {
    req = req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
  }
  return next(req);
};
