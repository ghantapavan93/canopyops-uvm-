import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

interface Cmd {
  label: string;
  hint?: string;
  icon: string;
  route?: string;
  href?: string;
}

const COMMANDS: Cmd[] = [
  { label: 'Program Overview', hint: 'live KPIs, lifecycle, activity', icon: '▦', route: '/console/overview' },
  { label: 'Command Center', hint: 'map + prioritized queue', icon: '◎', route: '/console/command' },
  { label: 'Risk Intelligence', hint: 'explainable span risk scoring', icon: '⚠', route: '/console/risk' },
  { label: 'Treatment Plan Builder', hint: 'draw + prescribe', icon: '✎', route: '/console/plan' },
  { label: 'Field Execution', hint: 'offline capture', icon: '⛏', route: '/console/execution' },
  { label: 'Sync & Conflict Center', hint: 'idempotent sync, conflicts', icon: '⇅', route: '/console/sync' },
  { label: 'Outcome Verification', hint: 'evidence gate, Proof Pack', icon: '✓', route: '/console/verification' },
  { label: 'Field Safety · Geofence', hint: 'proximity alerts, offline', icon: '🛰', route: '/console/geofence' },
  { label: '3D Terrain', hint: 'elevation, slope profile', icon: '⛰', route: '/console/terrain' },
  { label: 'Stewardship', hint: 'IVM, compliance', icon: '❋', route: '/console/stewardship' },
  { label: 'Integration · OData', hint: 'WBS / CATS, SAP seam', icon: '🔌', route: '/console/integration' },
  { label: 'Engineering Evidence', hint: 'tests, health, boundaries', icon: '⚙', route: '/console/engineering' },
  { label: 'Compliance Report', hint: 'print / save as PDF', icon: '📋', route: '/report' },
  { label: 'Open API docs (Swagger)', hint: '/api/docs', icon: '❯', href: '/api/docs' },
  { label: 'Prometheus metrics', hint: '/api/metrics/prometheus', icon: '❯', href: '/api/metrics/prometheus' },
  { label: 'Back to landing', hint: 'marketing page', icon: '❦', route: '/' },
];

/** A global command palette (⌘/Ctrl-K) — jump to any module or resource, with
 *  type-to-filter and full keyboard control. The hallmark of a power-user UI. */
@Component({
  selector: 'app-command-palette',
  standalone: true,
  template: `
    @if (open()) {
      <div class="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-[12vh]"
           (click)="close()" role="dialog" aria-modal="true" aria-label="Command palette">
        <div class="w-full max-w-lg overflow-hidden rounded-xl border border-border bg-surface shadow-pop"
             (click)="$event.stopPropagation()">
          <input #box type="text" [value]="query()" (input)="onInput($any($event.target).value)"
                 placeholder="Jump to… (type to filter)"
                 class="w-full border-b border-border bg-bg px-4 py-3 text-sm text-ink outline-none placeholder:text-muted"
                 aria-label="Search commands" />
          <ul class="max-h-80 overflow-y-auto py-1">
            @for (c of results(); track c.label; let i = $index) {
              <li>
                <button type="button" (click)="run(c)" (mouseenter)="active.set(i)"
                        class="flex w-full items-center gap-3 px-4 py-2 text-left text-sm"
                        [class.bg-primary-soft]="i === active()">
                  <span class="w-5 text-center" aria-hidden="true">{{ c.icon }}</span>
                  <span class="text-ink">{{ c.label }}</span>
                  @if (c.hint) { <span class="ml-auto truncate text-xs text-muted">{{ c.hint }}</span> }
                </button>
              </li>
            } @empty {
              <li class="px-4 py-6 text-center text-sm text-muted">No matches.</li>
            }
          </ul>
          <div class="flex items-center gap-3 border-t border-border px-4 py-1.5 text-xs text-muted">
            <span><kbd class="rounded border border-border px-1">↑↓</kbd> navigate</span>
            <span><kbd class="rounded border border-border px-1">↵</kbd> open</span>
            <span><kbd class="rounded border border-border px-1">esc</kbd> close</span>
            <span class="ml-auto"><kbd class="rounded border border-border px-1">⌘</kbd><kbd class="rounded border border-border px-1">K</kbd></span>
          </div>
        </div>
      </div>
    }
  `,
})
export class CommandPaletteComponent {
  private router = inject(Router);

  readonly open = signal(false);
  readonly query = signal('');
  readonly active = signal(0);

  readonly results = computed<Cmd[]>(() => {
    const q = this.query().trim().toLowerCase();
    if (!q) return COMMANDS;
    return COMMANDS.filter((c) => (c.label + ' ' + (c.hint ?? '')).toLowerCase().includes(q));
  });

  @HostListener('document:keydown', ['$event'])
  onKey(ev: KeyboardEvent): void {
    if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') {
      ev.preventDefault();
      this.toggle();
      return;
    }
    if (!this.open()) return;
    if (ev.key === 'Escape') { this.close(); ev.preventDefault(); }
    else if (ev.key === 'ArrowDown') { this.move(1); ev.preventDefault(); }
    else if (ev.key === 'ArrowUp') { this.move(-1); ev.preventDefault(); }
    else if (ev.key === 'Enter') {
      const c = this.results()[this.active()];
      if (c) this.run(c);
      ev.preventDefault();
    }
  }

  private toggle(): void {
    if (this.open()) { this.close(); return; }
    this.show();
  }
  /** Open the palette (e.g. from a header button) and focus the search box. */
  show(): void {
    this.open.set(true);
    this.query.set('');
    this.active.set(0);
    queueMicrotask(() => (document.querySelector('app-command-palette input') as HTMLInputElement)?.focus());
  }
  close(): void { this.open.set(false); }

  onInput(v: string): void {
    this.query.set(v);
    this.active.set(0);
  }

  private move(delta: number): void {
    const n = this.results().length;
    if (!n) return;
    this.active.set((this.active() + delta + n) % n);
  }

  run(c: Cmd): void {
    this.close();
    if (c.href) { window.open(c.href, '_blank', 'noopener'); return; }
    if (c.route) void this.router.navigateByUrl(c.route);
  }
}
