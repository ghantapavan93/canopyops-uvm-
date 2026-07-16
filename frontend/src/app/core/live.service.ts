import { Injectable, inject, signal } from '@angular/core';
import { Subject } from 'rxjs';

import { environment } from '../../environments/environment';
import { AuthService } from './auth.service';

/** Server push (SSE) for live invalidation.
 *
 *  Deliberately uses `fetch` + ReadableStream rather than the built-in
 *  EventSource: EventSource cannot send request headers, which would force the
 *  JWT into the query string (logged by every proxy). With fetch the token stays
 *  in an Authorization header.
 *
 *  The stream carries a *signal*, not data — on `treatments.changed` the caller
 *  refetches whatever page it is showing through the normal, tenant-scoped read
 *  path. Reconnects with exponential backoff; `connected` lets callers stand
 *  down their polling fallback while push is healthy.
 */
@Injectable({ providedIn: 'root' })
export class LiveService {
  private auth = inject(AuthService);

  /** True while the server has greeted us and the stream is healthy. */
  readonly connected = signal(false);

  private readonly _events = new Subject<string>();
  /** Emits the SSE event name (e.g. 'treatments.changed'). */
  readonly events = this._events.asObservable();

  private abort?: AbortController;
  private retry = 0;
  private running = false;
  /** Generation counter. Every connect/disconnect invalidates prior loops.
   *  A plain `stopped` flag is NOT enough: a loop parked in its backoff sleep
   *  would observe the flag only after waking, and by then a later connect()
   *  may have cleared it — resurrecting the old loop alongside the new one.
   *  Two live loops mean two open streams, and browsers allow only ~6
   *  connections per origin over HTTP/1.1, so the extras starve every XHR. */
  private epoch = 0;

  /** Open the stream (idempotent). */
  connect(): void {
    if (this.running) return;
    this.running = true;
    void this.loop(++this.epoch);
  }

  disconnect(): void {
    this.epoch++; // invalidate any in-flight loop
    this.running = false;
    this.abort?.abort();
    this.abort = undefined;
    this.connected.set(false);
  }

  private async loop(epoch: number): Promise<void> {
    while (epoch === this.epoch) {
      try {
        await this.readStream(epoch);
      } catch {
        /* network/abort — fall through to backoff below */
      }
      if (epoch !== this.epoch) break;
      this.connected.set(false);
      // Back off so a server restart doesn't turn into a reconnect storm.
      const wait = Math.min(30_000, 1_000 * 2 ** this.retry++);
      await new Promise((r) => setTimeout(r, wait));
    }
    // Only the current generation owns the flag.
    if (epoch === this.epoch) this.running = false;
  }

  private async readStream(epoch: number): Promise<void> {
    const ctrl = new AbortController();
    this.abort = ctrl;
    const headers: Record<string, string> = { Accept: 'text/event-stream' };
    const token = this.auth.token;
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(`${environment.apiBase}/events/stream`, {
      headers,
      signal: ctrl.signal,
    });
    if (!res.ok || !res.body) throw new Error(`SSE failed: ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      // A superseded generation must release its connection immediately —
      // holding it would eat one of the origin's ~6 HTTP/1.1 slots.
      if (epoch !== this.epoch) {
        ctrl.abort();
        return;
      }
      const { done, value } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      // SSE frames are separated by a blank line.
      let split: number;
      while ((split = buffer.indexOf('\n\n')) >= 0) {
        this.handleFrame(buffer.slice(0, split), epoch);
        buffer = buffer.slice(split + 2);
      }
    }
  }

  private handleFrame(frame: string, epoch: number): void {
    if (epoch !== this.epoch) return; // stale generation — drop it
    const trimmed = frame.trim();
    if (!trimmed || trimmed.startsWith(':')) return; // keepalive comment
    let name = 'message';
    for (const line of trimmed.split('\n')) {
      if (line.startsWith('event:')) name = line.slice(6).trim();
    }
    if (name === 'hello') {
      this.retry = 0;
      this.connected.set(true);
      return;
    }
    this._events.next(name);
  }
}
