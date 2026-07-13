import { Injectable, signal } from '@angular/core';

import { OutboxItem } from './models';

const DB_NAME = 'canopyops';
const STORE = 'outbox';
const VERSION = 1;

/** IndexedDB-backed outbox. Field mutations are written here first so they
 *  survive offline periods and full page refreshes — the durable local queue
 *  that the sync engine drains. Raw IndexedDB (no dependency) wrapped in
 *  promises + an Angular signal so the UI stays reactive. */
@Injectable({ providedIn: 'root' })
export class OutboxService {
  private dbPromise = this.open();
  readonly items = signal<OutboxItem[]>([]);

  constructor() {
    this.refresh();
  }

  private open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: 'id' });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  private async tx(mode: IDBTransactionMode): Promise<IDBObjectStore> {
    const db = await this.dbPromise;
    return db.transaction(STORE, mode).objectStore(STORE);
  }

  private wrap<T>(req: IDBRequest<T>): Promise<T> {
    return new Promise((resolve, reject) => {
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async getAll(): Promise<OutboxItem[]> {
    const store = await this.tx('readonly');
    const all = await this.wrap(store.getAll() as IDBRequest<OutboxItem[]>);
    return all.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  }

  async put(item: OutboxItem): Promise<void> {
    const store = await this.tx('readwrite');
    await this.wrap(store.put(item));
    await this.refresh();
  }

  async remove(id: string): Promise<void> {
    const store = await this.tx('readwrite');
    await this.wrap(store.delete(id));
    await this.refresh();
  }

  async clearSynced(): Promise<void> {
    const synced = (await this.getAll()).filter((i) => i.status === 'synced');
    const store = await this.tx('readwrite');
    await Promise.all(synced.map((i) => this.wrap(store.delete(i.id))));
    await this.refresh();
  }

  async refresh(): Promise<void> {
    this.items.set(await this.getAll());
  }
}
