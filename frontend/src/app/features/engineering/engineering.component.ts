import { Component, OnDestroy, inject, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import { SystemHealth } from '../../core/models';

interface Section {
  title: string;
  glyph: string;
  items: { label: string; detail: string; ok?: boolean }[];
}

/** Engineering Evidence — a reviewer-facing summary of what is actually built,
 *  tested, and bounded. Kept honest: authored-but-not-run items are labeled. */
@Component({
  selector: 'app-engineering',
  standalone: true,
  templateUrl: './engineering.component.html',
})
export class EngineeringComponent implements OnDestroy {
  private api = inject(ApiService);
  /** Live observability feed from the API's in-process metrics registry. */
  readonly health = signal<SystemHealth | null>(null);
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    const poll = () =>
      this.api.getMetrics().subscribe({ next: (h) => this.health.set(h), error: () => {} });
    poll();
    this.timer = setInterval(poll, 5000);
  }
  ngOnDestroy(): void {
    if (this.timer) clearInterval(this.timer);
  }

  readonly tests: Section = {
    title: 'Automated tests',
    glyph: '✓',
    items: [
      { label: 'Backend API (pytest) — 70 passing', ok: true, detail: 'idempotent replay, revision conflict (409) + resolve-under-same-key, evidence-completeness gate, RBAC (403), PostGIS coverage math, full plan→verify→close loop; plus plan creation + validation (422 structured envelope), overview periods, stewardship real signals, choropleth, geometry analysis, OpenAPI, GeoJSON import, metrics endpoint, pagination, the OData integration surface ($metadata, $filter/$select/$expand, deferred nav, ETag/304, and $batch — many reads in one round-trip with dependsOn 424 short-circuiting and a read-only 501 guard), the activity-date-scoped compliance rollup, reliability (statement_timeout cancels a runaway query, the in-flight limiter sheds load with 503 while probes stay answerable, /metrics exposes the concurrency + pool surface), geofence proximity alerts (PostGIS ST_Distance/ST_Contains → clear/warning/breach), the versioned offline zones snapshot (ETag/304), and the 3D terrain DEM grid + corridor elevation/slope profile' },
      { label: 'Frontend units (Jest) — 25 passing', ok: true, detail: 'coverage geometry math (slider % = area %), status presentation system (text+shape+tone, never color-only), StatusBadge component render, chart color/id utilities, and the on-device geofence engine — point-in-polygon, distance-to-boundary in metres, clear/warning/entered/breach escalation matching the server, and MultiPolygon parity with PostGIS' },
      { label: 'Cypress e2e — 8 passing (6 specs)', ok: true, detail: 'critical journey (plan → offline execution → partial upload → conflict recovery → evidence retry → verification → targeted follow-up → close → Proof Pack); the command palette (Ctrl/Cmd-K open, type-to-filter, keyboard + header-button navigation, Escape); the risk sign-off lifecycle (RBAC gate → certified reviewer signs off → append-only history → revoke reopens the span); the compliance report (rollup render, circuit + activity-date scoping, real PDF export); the OData $batch panel (several reads in a single POST, per-id statuses); and the not-found route (real 404 with a path back into the console). Runs headless (Electron) against the running stack via `npm run e2e`; verified green (~10s). The service worker is skipped under Cypress so it can never intercept e2e navigations.' },
    ],
  };

  readonly assurance: Section = {
    title: 'Assurance guarantees (server-enforced)',
    glyph: '🛡',
    items: [
      { label: 'Idempotency', ok: true, detail: 'Every mobile mutation carries an Idempotency-Key; replays and concurrent double-submits return the original record — zero duplicates.' },
      { label: 'Revision conflict', ok: true, detail: 'A stale offline edit returns 409 with local-vs-server revisions for human resolution. Never last-write-wins.' },
      { label: 'Evidence gate', ok: true, detail: 'A failed upload keeps the record incomplete and blocks verification until recovered.' },
      { label: 'Human-authored outcome', ok: true, detail: 'The API never declares a site effective, safe, or compliant. Conclusions are reviewer-authored and evidence-linked.' },
    ],
  };

  readonly architecture: Section = {
    title: 'Architecture',
    glyph: '⚙',
    items: [
      { label: 'Frontend', detail: 'Angular 18 (standalone, Signals + RxJS), MapLibre GL with switchable basemaps — real OSM streets / Esri World Imagery satellite (with attribution) layered under the synthetic operational data, or a fully self-contained offline style — IndexedDB outbox, Tailwind design tokens, CSS-driven motion (compositor-based; robust when a tab is backgrounded, and never gates content visibility).' },
      { label: 'Backend', detail: 'FastAPI modular monolith, SQLAlchemy 2 + GeoAlchemy2, Alembic migrations, JWT auth + role-based access, structured error envelopes + correlation IDs.' },
      { label: 'Data', detail: 'PostgreSQL 16 + PostGIS: server-side spatial filtering (ST_Intersects, ST_MakeEnvelope), GIST indexes on all geometry columns.' },
      { label: 'Offline-first PWA', detail: 'Installable web app: an Angular service worker precaches the app shell (HTML/JS/CSS + manifest) and caches read-only API GETs with a network-first (freshness) strategy, so the whole console loads and shows last-known data with no connectivity — layered on the IndexedDB outbox (queued mutations) and the on-device geofence engine. A version-ready handler prompts and reloads on new deploys.' },
      { label: 'Delivery', detail: 'Docker Compose (web + api + db), one-command local environment, GitHub Actions lint/test/build.' },
    ],
  };

  readonly accessibility: Section = {
    title: 'Accessibility',
    glyph: '♿',
    items: [
      { label: 'Non-color status', ok: true, detail: 'Every status carries text + a shape glyph + color (WCAG 1.4.1).' },
      { label: 'Keyboard + focus', ok: true, detail: 'Interactive elements are buttons/links with a visible focus ring; the map has a synchronized accessible list equivalent.' },
      { label: 'Semantics', ok: true, detail: 'Landmarks, aria-pressed/aria-current, live status regions, labelled controls.' },
      { label: 'Reduced motion', ok: true, detail: 'All GSAP and CSS animation is disabled under prefers-reduced-motion.' },
    ],
  };

  readonly matrix: Section = {
    title: 'Cross-browser & viewport',
    glyph: '🖥',
    items: [
      { label: 'Browsers', detail: 'Chrome, Edge, Firefox, Safari — standard web platform + MapLibre WebGL; no browser-specific APIs.' },
      { label: 'Viewports', detail: 'Responsive desktop / tablet / mobile via Tailwind breakpoints; field screens are mobile-first with large touch targets.' },
      { label: 'Performance (measured, 1,006 features)', detail: 'Server-side bbox spatial filter returned a bounded 164-feature subset in ~53 ms vs ~380 ms unfiltered — the ST_Intersects + GIST-index path keeps large sets off the client. Plus lazy-loaded routes and optimistic UI only for reversible edits.' },
    ],
  };

  readonly boundaries: Section = {
    title: 'Security & responsibility boundaries',
    glyph: '⚖',
    items: [
      { label: 'Synthetic only', detail: 'No real utility, worker, location, chemical, or client data. Not affiliated with The Davey Tree Expert Company.' },
      { label: 'RBAC on the server', detail: 'Authorization is enforced in the API, not just hidden in the UI. Evidence keys are opaque.' },
      { label: 'No pesticide advice', detail: 'The system records treatment categories; it never recommends products, rates, or mixing.' },
      { label: 'No AI verdicts', detail: 'Deterministic rules + human approval; certification/label compliance remain human responsibilities.' },
    ],
  };

  readonly limitations = [
    'Map uses a self-contained synthetic style (no basemap tiles) — deliberate, to stay offline-capable and free of external calls.',
    'Metrics shown in the console are synthetic and labeled as such; no real rework-rate statistics are claimed.',
    'Remote-sensing (LiDAR/multispectral) is modelled as an attach-ready data shape, not implemented.',
  ];

  readonly integration: Section = {
    title: 'Integration surfaces (real & testable)',
    glyph: '🔌',
    items: [
      { label: 'OData v4 service (SAP-style)', ok: true, detail: 'Live at /api/odata/ with $metadata (EDMX). Maps the domain to SAP concepts — treatment plan → WBS element, field execution → CATS time confirmation — and implements the patterns the role calls for: server paging ($top/$skip + nextLink), $filter (with parenthesised grouping + and/or precedence) / $select / $orderby / $expand, deferred navigation, ETag/If-None-Match caching (304), and $batch — many reads in one round-trip with dependsOn 424 short-circuiting (read-only, so writes return 501). The Integration console page consumes it with an app-level ETag cache and a live $batch panel. Synthetic facade, not a real SAP link.' },
      { label: 'Live OpenAPI 3 contract', ok: true, detail: 'Typed contract at /api/docs (Swagger), /api/redoc, /api/openapi.json — any external system can generate a client. This is the seam a utility integrates against.' },
      { label: 'Bring-your-own-data import', ok: true, detail: 'POST /api/import/corridors ingests a standard GeoJSON FeatureCollection of ROW centerlines — load real geometry and watch it render on the map.' },
      { label: 'Repository / adapter seam', ok: true, detail: 'The API depends on typed models, not data sources; synthetic swaps to real GIS / EAM / field-sync behind the same contracts (see docs/INTEGRATION.md).' },
      { label: 'Auth → SSO-ready', ok: true, detail: 'Synthetic JWT + server-enforced RBAC today; swap the token issuer for OIDC/SSO without touching enforcement.' },
      { label: 'Evidence object-storage abstraction', ok: true, detail: 'Opaque storage keys; point the adapter at S3/Azure Blob for production.' },
    ],
  };

  readonly reliability: Section = {
    title: 'Scalability & reliability',
    glyph: '📈',
    items: [
      { label: 'Graceful load-shedding', ok: true, detail: 'A bounded in-flight limiter (MAX_CONCURRENT_REQUESTS, default 64/worker) sheds excess requests with 503 + Retry-After instead of letting an unbounded queue turn one overload into a timeout for everyone. Health/readiness probes are exempt, so an orchestrator can still tell "overloaded" from "down". Shed count + live in-flight are exposed at /api/metrics.' },
      { label: 'Bounded query time', ok: true, detail: 'Every pooled connection carries a Postgres statement_timeout (default 15s), so a runaway query is cancelled server-side rather than pinning a connection forever. Verified by a test that a 2s query under a 250ms budget is cancelled.' },
      { label: 'Connection-pool tuning', ok: true, detail: 'Sized pool (DB_POOL_SIZE + DB_MAX_OVERFLOW) with pre-ping (survives Postgres restarts / idle drops) and periodic recycling (dodges stale sockets behind proxies). Pool checkout/overflow is live at /api/metrics.' },
      { label: 'Horizontal scale (stateless)', ok: true, detail: 'The API is stateless — a session per request, all shared state in Postgres — so WEB_CONCURRENCY spreads it across worker processes (and replicas) with no sticky sessions. Uvicorn drains in-flight requests on shutdown for zero-drop deploys. Trade-off noted honestly: the in-process metrics registry is per-worker, so a multi-worker deployment scrapes each worker (Prometheus endpoint provided).' },
      { label: 'Safe retries by construction', ok: true, detail: 'Because mutations are idempotent (Idempotency-Key) and conflicts are explicit (409 on stale revision), a client — or a load balancer — can retry safely; load-shed 503s and transient drops never risk a duplicate or a silent overwrite.' },
    ],
  };

  readonly sections: Section[] = [
    this.tests, this.integration, this.reliability, this.assurance, this.architecture,
    this.accessibility, this.matrix, this.boundaries,
  ];
}
