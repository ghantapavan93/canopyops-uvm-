import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../environments/environment';
import { AuthUser, Role } from './models';

interface TokenResponse {
  accessToken: string;
  user: AuthUser;
}

const TOKEN_KEY = 'canopyops.token';
const USER_KEY = 'canopyops.user';

/** Synthetic auth. Holds the JWT + current user as signals so role-aware UI
 *  reacts everywhere. Server still enforces authorization on every request. */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);

  private _user = signal<AuthUser | null>(this.restoreUser());
  readonly user = this._user.asReadonly();
  readonly role = computed<Role | null>(() => this._user()?.role ?? null);
  readonly isAuthenticated = computed(() => this._user() !== null);

  get token(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  }

  async login(email: string, password: string): Promise<void> {
    const body = new URLSearchParams({ username: email, password });
    const res = await firstValueFrom(
      this.http.post<TokenResponse>(`${environment.apiBase}/auth/token`, body.toString(), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      }),
    );
    localStorage.setItem(TOKEN_KEY, res.accessToken);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    this._user.set(res.user);
  }

  logout(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    this._user.set(null);
  }

  /** Does the current user hold any of the given roles? Drives role-aware UI. */
  can(...roles: Role[]): boolean {
    const r = this.role();
    return r !== null && roles.includes(r);
  }

  private restoreUser(): AuthUser | null {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  }
}
