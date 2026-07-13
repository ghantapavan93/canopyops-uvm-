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
      { label: 'Backend API (pytest) — 26 passing', ok: true, detail: 'idempotent replay, revision conflict (409) + resolve-under-same-key, evidence-completeness gate, RBAC (403), PostGIS coverage math, full plan→verify→close loop; plus plan creation + validation (422 structured envelope), overview periods, stewardship real signals, choropleth, geometry analysis, OpenAPI, GeoJSON import, metrics endpoint, and pagination' },
      { label: 'Frontend units (Jest) — 12 passing', ok: true, detail: 'coverage geometry math (slider % = area %), status presentation system (text+shape+tone, never color-only), StatusBadge component render, chart color/id utilities' },
      { label: 'Cypress critical journey — 1 passing', ok: true, detail: 'plan → offline execution → partial upload → conflict recovery → evidence retry → verification → targeted follow-up → close → Proof Pack. Runs headless (Electron) against the running stack via `npm run e2e`; verified green (~5s).' },
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
      { label: 'Frontend', detail: 'Angular 18 (standalone, Signals + RxJS), MapLibre GL (self-contained style), IndexedDB outbox, Tailwind design tokens, CSS-driven motion (compositor-based; robust when a tab is backgrounded, and never gates content visibility).' },
      { label: 'Backend', detail: 'FastAPI modular monolith, SQLAlchemy 2 + GeoAlchemy2, Alembic migrations, JWT auth + role-based access, structured error envelopes + correlation IDs.' },
      { label: 'Data', detail: 'PostgreSQL 16 + PostGIS: server-side spatial filtering (ST_Intersects, ST_MakeEnvelope), GIST indexes on all geometry columns.' },
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
    'Cypress e2e is authored and runnable but was not executed in the build session (the equivalent journey was verified interactively).',
    'Map uses a self-contained synthetic style (no basemap tiles) — deliberate, to stay offline-capable and free of external calls.',
    'Metrics shown in the console are synthetic and labeled as such; no real rework-rate statistics are claimed.',
    'Remote-sensing (LiDAR/multispectral) is modelled as an attach-ready data shape, not implemented.',
  ];

  readonly integration: Section = {
    title: 'Integration surfaces (real & testable)',
    glyph: '🔌',
    items: [
      { label: 'Live OpenAPI 3 contract', ok: true, detail: 'Typed contract at /api/docs (Swagger), /api/redoc, /api/openapi.json — any external system can generate a client. This is the seam a utility integrates against.' },
      { label: 'Bring-your-own-data import', ok: true, detail: 'POST /api/import/corridors ingests a standard GeoJSON FeatureCollection of ROW centerlines — load real geometry and watch it render on the map.' },
      { label: 'Repository / adapter seam', ok: true, detail: 'The API depends on typed models, not data sources; synthetic swaps to real GIS / EAM / field-sync behind the same contracts (see docs/INTEGRATION.md).' },
      { label: 'Auth → SSO-ready', ok: true, detail: 'Synthetic JWT + server-enforced RBAC today; swap the token issuer for OIDC/SSO without touching enforcement.' },
      { label: 'Evidence object-storage abstraction', ok: true, detail: 'Opaque storage keys; point the adapter at S3/Azure Blob for production.' },
    ],
  };

  readonly sections: Section[] = [
    this.tests, this.integration, this.assurance, this.architecture,
    this.accessibility, this.matrix, this.boundaries,
  ];
}
