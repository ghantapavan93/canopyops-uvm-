import { Injectable } from '@angular/core';

import { EnvironmentalConstraint } from './models';

export interface ZoneSnapshot {
  version: string;
  zones: EnvironmentalConstraint[];
  cachedAt: string;
}

const DB_NAME = 'canopyops-geo';
const STORE = 'kv';
const KEY = 'zones-snapshot';

/** Durable IndexedDB cache for the protected-zone snapshot, so the geofence
 *  works after a full refresh with no connectivity. Separate database from the
 *  outbox to avoid version coupling; raw IndexedDB, no dependency. */
@Injectable({ providedIn: 'root' })
export class ZoneCacheService {
  private dbPromise = this.open();

  private open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  private wrap<T>(req: IDBRequest<T>): Promise<T> {
    return new Promise((resolve, reject) => {
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async save(snapshot: ZoneSnapshot): Promise<void> {
    const db = await this.dbPromise;
    const store = db.transaction(STORE, 'readwrite').objectStore(STORE);
    await this.wrap(store.put(snapshot, KEY));
  }

  async load(): Promise<ZoneSnapshot | null> {
    const db = await this.dbPromise;
    const store = db.transaction(STORE, 'readonly').objectStore(STORE);
    return (await this.wrap(store.get(KEY) as IDBRequest<ZoneSnapshot>)) ?? null;
  }
}
