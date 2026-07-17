import { Component, HostListener, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from '../../core/auth.service';
import { ConnectivityService } from '../../core/connectivity.service';
import { DEMO_PASSWORD, DEMO_USERS } from '../../core/demo-users';
import { Role } from '../../core/models';
import { SyncService } from '../../core/sync.service';
import { CommandPaletteComponent } from '../../shared/command-palette.component';

interface NavItem {
  label: string;
  route?: string;
  glyph: string;
  ready: boolean;
}

interface NavGroup {
  title: string;
  items: NavItem[];
}

/** The rail, grouped by what a person is trying to DO.
 *
 *  Fifteen flat destinations made the product look bigger and read smaller — a
 *  reviewer couldn't tell the core loop (plan → execute → recover → verify →
 *  prove) from the supporting surfaces. The order is the story: Operations sets
 *  the work, Field does it, Assurance judges it, Intelligence informs it, and
 *  Engineering is the proof for a technical reader.
 */
const NAV_GROUPS: NavGroup[] = [
  {
    title: 'Operations',
    items: [
      { label: 'Program Overview', route: '/console/overview', glyph: '▦', ready: true },
      { label: 'Command Center', route: '/console/command', glyph: '◎', ready: true },
      { label: 'Treatment Plan', route: '/console/plan', glyph: '✎', ready: true },
    ],
  },
  {
    title: 'Field',
    items: [
      { label: 'Field Execution', route: '/console/execution', glyph: '⛏', ready: true },
      { label: 'Sync & Conflict', route: '/console/sync', glyph: '⇅', ready: true },
      { label: 'Field Safety · Geofence', route: '/console/geofence', glyph: '🛰', ready: true },
    ],
  },
  {
    title: 'Assurance',
    items: [
      { label: 'Outcome Verification', route: '/console/verification', glyph: '✓', ready: true },
      { label: 'Quality & Compliance', route: '/console/audit', glyph: '📋', ready: true },
      { label: 'Stewardship', route: '/console/stewardship', glyph: '❋', ready: true },
    ],
  },
  {
    title: 'Intelligence',
    items: [
      { label: 'Risk Intelligence', route: '/console/risk', glyph: '⚠', ready: true },
      { label: 'Vegetation Intelligence', route: '/console/vegetation', glyph: '🌿', ready: true },
      { label: '3D Terrain', route: '/console/terrain', glyph: '⛰', ready: true },
    ],
  },
  {
    title: 'Engineering',
    items: [
      { label: 'Integration · OData', route: '/console/integration', glyph: '🔌', ready: true },
      { label: 'Engineering Evidence', route: '/console/engineering', glyph: '⚙', ready: true },
      { label: 'Compliance Report', route: '/report', glyph: '📋', ready: true },
    ],
  },
];

@Component({
  selector: 'app-console-shell',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, CommandPaletteComponent],
  template: `
    <div class="flex h-screen flex-col bg-bg text-ink">
      <!-- Synthetic-data banner: honesty is a first-class requirement -->
      <div
        class="flex items-center justify-center gap-2 bg-warn-soft px-4 py-1 text-center text-xs text-warn"
        role="note"
      >
        <span aria-hidden="true">⚠</span>
        Synthetic demonstration data. Independent concept — not affiliated with or
        endorsed by The Davey Tree Expert Company.
      </div>

      <header
        class="flex h-14 flex-shrink-0 items-center gap-3 border-b border-border bg-surface px-4"
      >
        <!-- Mobile module menu: the rail is desktop-only, so a field crew on a
             phone reaches every module through this drawer. -->
        <button type="button" (click)="mobileNav.set(true)"
                class="-ml-1 grid h-9 w-9 place-items-center rounded-md text-ink hover:bg-surface-2 md:hidden"
                aria-label="Open navigation menu" [attr.aria-expanded]="mobileNav()">
          <span aria-hidden="true" class="text-lg">☰</span>
        </button>

        <a routerLink="/" class="flex items-center gap-2 no-underline">
          <span
            class="grid h-8 w-8 place-items-center rounded-md bg-primary text-primary-ink"
            aria-hidden="true"
          >❦</span>
          <span class="font-semibold tracking-tight text-ink">CanopyOps</span>
          <span class="hidden text-xs text-muted sm:inline">Treatment Assurance</span>
        </a>

        <button type="button" (click)="palette.show()"
                class="ml-3 hidden items-center gap-2 rounded-md border border-border px-2.5 py-1.5 text-xs text-muted hover:bg-surface-2 sm:flex"
                aria-label="Open command palette">
          <span aria-hidden="true">⌕</span> Jump to…
          <kbd class="rounded border border-border px-1 text-xs">⌘K</kbd>
        </button>

        <div class="ml-auto flex items-center gap-2">
          <span class="flex items-center gap-1.5 rounded-full border border-border px-2 py-1 text-xs font-medium"
                [class.text-ok]="conn.online()" [class.text-danger]="!conn.online()"
                [title]="conn.online() ? 'Connectivity: online' : 'Connectivity: offline (simulated)'">
            <span class="inline-block h-2 w-2 rounded-full" [class.bg-ok]="conn.online()" [class.bg-danger]="!conn.online()"
                  [class.live-dot]="conn.online()" [class.live-dot--danger]="!conn.online()"></span>
            {{ conn.online() ? 'Online' : 'Offline' }}
          </span>
          @if (auth.user()?.tenantName; as tenant) {
            <span class="hidden items-center gap-1 rounded-full border border-primary/40 bg-primary-soft px-2 py-1 text-xs font-semibold text-primary md:inline-flex"
                  title="Current program (tenant) — data is isolated per program">⧉ {{ tenant }}</span>
          }
          <span class="hidden text-xs text-muted md:inline">Acting as</span>
          <div class="hidden overflow-hidden rounded-md border border-border md:flex" role="group"
               aria-label="Switch synthetic role / program">
            @for (u of demoUsers; track u.key) {
              <button
                type="button"
                (click)="switchRole(u)"
                [class.bg-primary]="auth.user()?.email === u.email"
                [class.text-primary-ink]="auth.user()?.email === u.email"
                [attr.aria-pressed]="auth.user()?.email === u.email"
                class="px-2.5 py-1.5 text-xs font-medium text-ink transition-colors hover:bg-surface-2"
              >{{ u.label }}</button>
            }
          </div>
        </div>
      </header>

      <div class="flex min-h-0 flex-1">
        <!-- Module rail -->
        <nav
          class="hidden w-52 flex-shrink-0 flex-col gap-0.5 border-r border-border bg-surface p-2 md:flex"
          aria-label="Modules"
        >
          @for (group of navGroups; track group.title) {
            <div class="mb-0.5 mt-3 px-3 text-xs font-semibold uppercase tracking-wide text-muted first:mt-0">
              {{ group.title }}
            </div>
            @for (item of group.items; track item.label) {
              <a
                [routerLink]="item.route"
                routerLinkActive="bg-primary-soft text-primary font-semibold"
                class="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm text-ink no-underline hover:bg-surface-2"
              >
                <span class="w-4 text-center" aria-hidden="true">{{ item.glyph }}</span>
                {{ item.label }}
                @if (item.route === '/console/sync' && (sync.outstanding() + sync.conflicts()) > 0) {
                  <span class="ml-auto rounded-full px-1.5 py-0.5 text-xs font-bold"
                        [class.bg-danger]="sync.conflicts() > 0" [class.text-white]="sync.conflicts() > 0"
                        [class.bg-warn-soft]="sync.conflicts() === 0" [class.text-warn]="sync.conflicts() === 0">
                    {{ sync.outstanding() + sync.conflicts() }}
                  </span>
                }
              </a>
            }
          }
        </nav>

        <main class="min-w-0 flex-1 overflow-hidden">
          <router-outlet />
        </main>
      </div>

      <!-- Mobile navigation drawer (module rail is hidden below md) -->
      @if (mobileNav()) {
        <div class="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true"
             aria-label="Navigation menu">
          <div class="absolute inset-0 bg-black/50" (click)="mobileNav.set(false)"></div>
          <nav class="absolute left-0 top-0 flex h-full w-72 max-w-[82%] flex-col gap-1 overflow-y-auto border-r border-border bg-surface p-3 shadow-pop"
               aria-label="Modules">
            <div class="mb-2 flex items-center justify-between">
              <span class="font-semibold text-ink">CanopyOps</span>
              <button type="button" (click)="mobileNav.set(false)"
                      class="grid h-8 w-8 place-items-center rounded-md text-ink hover:bg-surface-2"
                      aria-label="Close navigation menu">
                <span aria-hidden="true">✕</span>
              </button>
            </div>

            <!-- Role/program switch (synthetic) also lives here on mobile, where
                 the header switcher is hidden to avoid overflow. -->
            <div class="mb-1 text-xs uppercase tracking-wide text-muted">Acting as</div>
            <div class="mb-3 grid grid-cols-2 gap-1" role="group" aria-label="Switch synthetic role / program">
              @for (u of demoUsers; track u.key) {
                <button type="button" (click)="switchRole(u); mobileNav.set(false)"
                        [class.bg-primary]="auth.user()?.email === u.email"
                        [class.text-primary-ink]="auth.user()?.email === u.email"
                        [attr.aria-pressed]="auth.user()?.email === u.email"
                        class="rounded-md border border-border px-2 py-1.5 text-xs font-medium text-ink hover:bg-surface-2">
                  {{ u.label }}
                </button>
              }
            </div>

            @for (group of navGroups; track group.title) {
              <div class="mb-0.5 mt-3 text-xs font-semibold uppercase tracking-wide text-muted first:mt-0">
                {{ group.title }}
              </div>
              @for (item of group.items; track item.label) {
                <a [routerLink]="item.route" (click)="mobileNav.set(false)"
                   routerLinkActive="bg-primary-soft text-primary font-semibold"
                   class="flex items-center gap-2.5 rounded-md px-3 py-2.5 text-sm text-ink no-underline hover:bg-surface-2">
                  <span class="w-4 text-center" aria-hidden="true">{{ item.glyph }}</span>
                  {{ item.label }}
                </a>
              }
            }
          </nav>
        </div>
      }

      <app-command-palette #palette />
    </div>
  `,
})
export class ConsoleShellComponent {
  readonly auth = inject(AuthService);
  readonly sync = inject(SyncService);
  readonly conn = inject(ConnectivityService);
  readonly demoUsers = DEMO_USERS;
  readonly role = this.auth.role;

  /** Mobile navigation drawer open state (the module rail is desktop-only). */
  readonly mobileNav = signal(false);

  @HostListener('document:keydown.escape')
  closeMobileNav(): void {
    if (this.mobileNav()) this.mobileNav.set(false);
  }

  readonly navGroups = NAV_GROUPS;

  async switchRole(u: { role: Role; email: string }): Promise<void> {
    // Synthetic quick-switch to demonstrate role-aware UI + server RBAC.
    try {
      const before = this.auth.user()?.tenantId;
      await this.auth.login(u.email, DEMO_PASSWORD);
      // Switching between two different PROGRAMS (tenants) must swap the whole
      // console's data. Component signals + the OData ETag cache hold the previous
      // program's rows, so a full reload of the current route is the reliable reset
      // (the URL is kept). Only reload on an actual program change — not on the
      // first sign-in (no prior tenant) or a same-program role switch.
      if (before != null && this.auth.user()?.tenantId !== before) {
        window.location.reload();
      }
    } catch {
      /* API may be offline during static preview; role UI still updates on retry */
    }
  }
}
