import { HttpClient, HttpErrorResponse, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

import { environment } from '../../environments/environment';

/** How a result was served — surfaced as live telemetry in the UI. */
export type OdataSource = 'network' | 'revalidated-304' | 'cache';

export interface OdataResult<T = Record<string, unknown>> {
  value: T[];
  count?: number;
  nextLink?: string;
  etag?: string;
  source: OdataSource;
  ms: number;
}

export interface OdataQuery {
  select?: string;
  filter?: string;
  orderby?: string;
  top?: number;
  skip?: number;
  expand?: string;
}

/** A minimal OData v4 client for the SAP-style integration seam.
 *
 *  Mirrors how an Angular front end consumes SAP OData: it holds an
 *  ETag-keyed response cache and revalidates with `If-None-Match`, so a repeat
 *  query costs a `304 Not Modified` (no body) instead of a full re-fetch, and a
 *  navigation property is only fetched when it's actually expanded (deferred
 *  loading). The server sends `Cache-Control: no-store`, so this app tier — not
 *  the browser — owns the cache and the 304s stay observable. */
@Injectable({ providedIn: 'root' })
export class OdataService {
  private http = inject(HttpClient);
  private base = `${environment.apiBase}/odata/`;
  private cache = new Map<string, { etag: string; body: any }>();

  /** Build an OData path with system query options, correctly encoded. */
  buildPath(entitySet: string, q: OdataQuery = {}): string {
    const parts: string[] = [];
    if (q.select) parts.push(`$select=${encodeURIComponent(q.select)}`);
    if (q.filter) parts.push(`$filter=${encodeURIComponent(q.filter)}`);
    if (q.orderby) parts.push(`$orderby=${encodeURIComponent(q.orderby)}`);
    if (q.top != null) parts.push(`$top=${q.top}`);
    if (q.skip != null) parts.push(`$skip=${q.skip}`);
    if (q.expand) parts.push(`$expand=${encodeURIComponent(q.expand)}`);
    parts.push('$count=true');
    return `${entitySet}?${parts.join('&')}`;
  }

  /** GET a collection with conditional revalidation. `path` is relative to the
   *  OData root (e.g. `WbsElements?$top=5` or `WbsElements('X')/CatsEntries`). */
  query<T = Record<string, unknown>>(path: string): Observable<OdataResult<T>> {
    const cached = this.cache.get(path);
    const t0 = performance.now();
    const headers: Record<string, string> = cached ? { 'If-None-Match': cached.etag } : {};
    return this.http
      .get<any>(this.base + path, { headers, observe: 'response' })
      .pipe(
        map((resp: HttpResponse<any>) => {
          const etag = resp.headers.get('ETag') ?? undefined;
          const body = resp.body ?? {};
          if (etag) this.cache.set(path, { etag, body });
          return this.shape<T>(body, etag, 'network', t0);
        }),
        catchError((err: HttpErrorResponse) => {
          if (err.status === 304 && cached) {
            return of(this.shape<T>(cached.body, cached.etag, 'revalidated-304', t0));
          }
          throw err;
        }),
      );
  }

  private shape<T>(body: any, etag: string | undefined, source: OdataSource, t0: number): OdataResult<T> {
    return {
      value: (body.value ?? []) as T[],
      count: body['@odata.count'],
      nextLink: body['@odata.nextLink'],
      etag,
      source,
      ms: Math.round((performance.now() - t0) * 10) / 10,
    };
  }

  /** Absolute URL for the raw response / $metadata (for inspector links). */
  url(path: string): string {
    return this.base + path;
  }
}
