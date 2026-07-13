import { Injectable, signal } from '@angular/core';

export type ToastTone = 'ok' | 'danger' | 'info';

export interface Toast {
  id: number;
  message: string;
  tone: ToastTone;
}

/** Lightweight global toast feedback. Non-technical users need to *know* an
 *  action worked (or didn't) — this gives every mutation a clear confirmation. */
@Injectable({ providedIn: 'root' })
export class ToastService {
  private seq = 0;
  readonly toasts = signal<Toast[]>([]);

  show(message: string, tone: ToastTone = 'ok', ttlMs = 4000): void {
    const id = ++this.seq;
    this.toasts.update((list) => [...list, { id, message, tone }]);
    setTimeout(() => this.dismiss(id), ttlMs);
  }

  success(message: string): void {
    this.show(message, 'ok');
  }
  error(message: string): void {
    this.show(message, 'danger', 6000);
  }
  info(message: string): void {
    this.show(message, 'info');
  }

  dismiss(id: number): void {
    this.toasts.update((list) => list.filter((t) => t.id !== id));
  }
}
