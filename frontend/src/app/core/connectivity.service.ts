import { Injectable, signal } from '@angular/core';

/** Tracks effective connectivity. In the field the network is intermittent, so
 *  the demo lets you force "offline" independent of the real browser state —
 *  the whole point is proving the app behaves when signal drops. */
@Injectable({ providedIn: 'root' })
export class ConnectivityService {
  // Simulated override: null = follow the browser; true/false = forced.
  private forced = signal<boolean | null>(null);
  private browserOnline = signal(navigator.onLine);

  readonly online = signal(navigator.onLine);

  constructor() {
    window.addEventListener('online', () => {
      this.browserOnline.set(true);
      this.recompute();
    });
    window.addEventListener('offline', () => {
      this.browserOnline.set(false);
      this.recompute();
    });
    this.recompute();
  }

  private recompute(): void {
    const forced = this.forced();
    this.online.set(forced === null ? this.browserOnline() : forced);
  }

  /** Demo control: flip the field radio on/off. */
  setForced(state: boolean): void {
    this.forced.set(state);
    this.recompute();
  }

  followBrowser(): void {
    this.forced.set(null);
    this.recompute();
  }

  get isForced(): boolean {
    return this.forced() !== null;
  }
}
