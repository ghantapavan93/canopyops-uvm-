import { Component, inject } from '@angular/core';

import { ToastService } from '../core/toast.service';

/** Renders global toasts (top-right). aria-live so screen readers announce them. */
@Component({
  selector: 'app-toast-container',
  standalone: true,
  template: `
    <div class="pointer-events-none fixed right-3 top-3 z-[100] flex w-80 max-w-[calc(100vw-1.5rem)] flex-col gap-2"
         aria-live="polite" aria-atomic="true">
      @for (t of toasts.toasts(); track t.id) {
        <div class="pointer-events-auto flex items-start gap-2 rounded-lg border bg-surface p-3 shadow-pop"
             style="animation: slide-in 0.22s cubic-bezier(0.2,0.7,0.2,1) both"
             [class.border-ok]="t.tone==='ok'" [class.border-danger]="t.tone==='danger'" [class.border-info]="t.tone==='info'"
             role="status">
          <span class="mt-0.5 flex-shrink-0 text-sm"
                [class.text-ok]="t.tone==='ok'" [class.text-danger]="t.tone==='danger'" [class.text-info]="t.tone==='info'"
                aria-hidden="true">{{ t.tone === 'ok' ? '✓' : t.tone === 'danger' ? '✕' : 'ℹ' }}</span>
          <span class="flex-1 text-sm text-ink">{{ t.message }}</span>
          <button (click)="toasts.dismiss(t.id)" class="text-muted hover:text-ink" aria-label="Dismiss">✕</button>
        </div>
      }
    </div>
  `,
})
export class ToastContainerComponent {
  readonly toasts = inject(ToastService);
}
