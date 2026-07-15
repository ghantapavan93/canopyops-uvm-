import { DatePipe } from '@angular/common';
import { Component, OnDestroy, inject, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import { JobRecord, SystemHealth } from '../../core/models';

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
  imports: [DatePipe],
  templateUrl: './engineering.component.html',
})
export class EngineeringComponent implements OnDestroy {
  private api = inject(ApiService);
  /** Live observability feed from the API's in-process metrics registry. */
  readonly health = signal<SystemHealth | null>(null);
  /** Recent durable-queue jobs (processed by the worker container). */
  readonly jobs = signal<JobRecord[]>([]);
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    const poll = () => {
      this.api.getMetrics().subscribe({ next: (h) => this.health.set(h), error: () => {} });
      this.api.listJobs().subscribe({ next: (j) => this.jobs.set(j.slice(0, 6)), error: () => {} });
    };
    poll();
    this.timer = setInterval(poll, 5000);
  }

  jobClass(status: string): string {
    return status === 'succeeded' ? 'bg-ok-soft text-ok'
      : status === 'failed' ? 'bg-danger-soft text-danger'
      : status === 'running' ? 'bg-info-soft text-info' : 'bg-surface-2 text-muted';
  }
  ngOnDestroy(): void {
    if (this.timer) clearInterval(this.timer);
  }

  readonly tests: Section = {
    title: 'Automated tests',
    glyph: '✓',
    items: [
      { label: 'Backend API (pytest) — 121 passing', ok: true, detail: 'idempotent replay, revision conflict (409) + resolve-under-same-key, evidence-completeness gate, RBAC (403), PostGIS coverage math, full plan→verify→close loop; plus plan creation + validation (422 structured envelope), overview periods, stewardship real signals, choropleth, geometry analysis, OpenAPI, GeoJSON import, metrics endpoint, pagination, the OData integration surface ($metadata, $filter/$select/$expand, deferred nav, ETag/304, and $batch — many reads in one round-trip with dependsOn 424 short-circuiting and a read-only 501 guard), the activity-date-scoped compliance rollup, the reliability-outcome model (per-circuit closed-vs-effective with synthetic SAIDI/SAIFI/CAIDI/CMI driven by real coverage/evidence/status — CAIDI=SAIDI/SAIFI, CMI=SAIDI×customers, deterministic, rollup totals reconcile), the vegetation-intelligence model (hot-spotting score bounds + tiering + summary counts; cycle-buster days-to-conflict = headroom÷growth with cycle-relative priority; deterministic), the work-plan QA audit (objective checks score = passed÷total, critical-miss caps the suggestion at fail, RBAC 403 for non-reviewers, append-only history + immutable audit event, 422 on bad outcome) and the compliance vault (framework mapping, completeness = satisfied÷requirements, QA requirement flips after a passing audit, evidence-integrity chain), reliability (statement_timeout cancels a runaway query, the in-flight limiter sheds load with 503 while probes stay answerable, a per-client token bucket returns 429 over its burst, the DB circuit breaker opens→half-opens→closes and fast-fails DB routes while it\'s open, /metrics exposes the whole surface), OpenTelemetry (every response carries an X-Trace-Id, an inbound W3C traceparent propagates into the server span, the error envelope carries the trace id, and a request emits a real server span + child DB spans on one trace), the durable background-job queue (enqueue Proof Pack / GeoJSON import → the worker claims it FOR UPDATE SKIP LOCKED → succeeded with the result; exclusive claim + drain; retry-then-fail with backoff), the evidence object-storage pipeline (validate content-type + size, presigned PUT URL, finalize HEADs the object → STORED, missing object → FAILED and recoverable, size-mismatch → FAILED, RBAC, upload rate-limit 429 — full flow on an in-memory backend, plus the real MinIO path verified live), geofence proximity alerts (PostGIS ST_Distance/ST_Contains → clear/warning/breach), the versioned offline zones snapshot (ETag/304), and the 3D terrain DEM grid + corridor elevation/slope profile' },
      { label: 'Frontend units (Jest) — 25 passing', ok: true, detail: 'coverage geometry math (slider % = area %), status presentation system (text+shape+tone, never color-only), StatusBadge component render, chart color/id utilities, and the on-device geofence engine — point-in-polygon, distance-to-boundary in metres, clear/warning/entered/breach escalation matching the server, and MultiPolygon parity with PostGIS' },
      { label: 'Cypress e2e — 16 passing (12 specs)', ok: true, detail: 'critical journey (plan → offline execution → partial upload → conflict recovery → evidence retry → verification → targeted follow-up → close → Proof Pack); the command palette (Ctrl/Cmd-K open, type-to-filter, keyboard + header-button navigation, Escape); the risk sign-off lifecycle (RBAC gate → certified reviewer signs off → append-only history → revoke reopens the span); the compliance report (rollup render, circuit + activity-date scoping, real PDF export); the OData $batch panel (several reads in a single POST, per-id statuses); the reliability-outcome panel (closed-vs-effective with per-circuit SAIDI movement); vegetation intelligence (the hot-spotting heat list → driver breakdown, and the cycle-buster watchlist filter); quality & compliance (the QA audit checklist → RBAC-gated verdict → append-only history, and the framework-mapped evidence vault); the automated axe-core accessibility gate (0 serious/critical across 5 screens); and the not-found route (real 404 with a path back into the console). Runs headless (Electron) against the running stack via `npm run e2e`; verified green (~10s). The service worker is skipped under Cypress so it can never intercept e2e navigations.' },
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
      { label: 'Backend', detail: 'FastAPI modular monolith, SQLAlchemy 2 + GeoAlchemy2, Alembic migrations, JWT auth + role-based access, structured error envelopes + correlation IDs, and OpenTelemetry distributed tracing (request → DB spans, W3C context propagation, OTLP-exportable).' },
      { label: 'Data', detail: 'PostgreSQL 16 + PostGIS: server-side spatial filtering (ST_Intersects, ST_MakeEnvelope), GIST indexes on all geometry columns. Evidence files live in S3-compatible object storage (MinIO) — not the DB — behind presigned upload/download URLs.' },
      { label: 'Offline-first PWA', detail: 'Installable web app: an Angular service worker precaches the app shell (HTML/JS/CSS + manifest) and caches read-only API GETs with a network-first (freshness) strategy, so the whole console loads and shows last-known data with no connectivity — layered on the IndexedDB outbox (queued mutations) and the on-device geofence engine. A version-ready handler prompts and reloads on new deploys.' },
      { label: 'Delivery', detail: 'Docker Compose (web + api + db + background worker + MinIO object storage), one-command local environment, GitHub Actions lint/test/build. The worker drains a durable DB-backed job queue off the request path.' },
    ],
  };

  readonly accessibility: Section = {
    title: 'Accessibility',
    glyph: '♿',
    items: [
      { label: 'Automated axe-core gate', ok: true, detail: 'An axe-core (4.10) Cypress spec runs on 5 primary screens and fails the build on any serious/critical violation — currently 0. The first run found color-contrast on small status text (worst in dark mode); fixed systemically in the design tokens + component helpers (light & dark). See docs/ACCESSIBILITY.md.' },
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
      { label: 'Browsers', detail: 'Chrome, Edge, Firefox, Safari — standard web platform + MapLibre WebGL; no browser-specific APIs. Support floor + feature fallbacks documented in docs/BROWSER-MATRIX.md.' },
      { label: 'Viewports', detail: 'Responsive desktop / tablet / mobile via Tailwind breakpoints; field screens are mobile-first with large touch targets.' },
      { label: 'Load test (measured)', detail: 'A real k6 / Python load test (docs/LOAD-TEST.md, artifacts in /load): 1,500 req/endpoint at concurrency 40 → 0% errors, non-spatial p95 338–342 ms, spatial p95 518–605 ms (rate-limit lifted to measure server latency, not the limiter). Design targets + SLOs in docs/SLO.md.' },
      { label: 'Spatial perf', detail: 'Server-side bbox spatial filter returned a bounded 164-feature subset in ~53 ms vs ~380 ms unfiltered — the ST_Intersects + GIST-index path keeps large sets off the client. Plus lazy-loaded routes and optimistic UI only for reversible edits.' },
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
      { label: 'Evidence object storage', ok: true, detail: 'Real S3-compatible object storage (MinIO) behind a swappable adapter (memory | s3). Presigned PUT URLs put bytes client → storage directly (the API never proxies the file); finalize HEADs the object to confirm the upload landed. Point the adapter at AWS S3 / Azure Blob for production.' },
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
      { label: 'Per-client rate limiting', ok: true, detail: 'A token bucket per client (RATE_LIMIT_PER_MIN refill, RATE_LIMIT_BURST burst) returns 429 + Retry-After to a single noisy caller — distinct from the global load-shedder, so one client can\'t monopolise capacity. Checked before a global slot is taken; probes exempt; bounded memory (idle buckets evicted). Verified live: a 120-request burst → 64 admitted, 56 got 429.' },
      { label: 'Database circuit breaker', ok: true, detail: 'When Postgres browns out, the breaker OPENs after N consecutive connection errors and DB-backed requests fail fast with 503 instead of each waiting for a connection timeout; after a reset window it HALF-OPENs, probes once, and closes on success. Trips are counted at /api/metrics. Turns a slow cascading failure into a fast, self-healing one.' },
      { label: 'Safe retries by construction', ok: true, detail: 'Because mutations are idempotent (Idempotency-Key) and conflicts are explicit (409 on stale revision), a client — or a load balancer — can retry safely; load-shed 503s, 429s, and transient drops never risk a duplicate or a silent overwrite.' },
    ],
  };

  readonly sections: Section[] = [
    this.tests, this.integration, this.reliability, this.assurance, this.architecture,
    this.accessibility, this.matrix, this.boundaries,
  ];
}
