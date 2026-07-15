# CanopyOps — Treatment Assurance

> **Closed is not the same as effective.**
> A completed work order proves an activity was *recorded*. It does not prove the
> intended vegetation *outcome* occurred. CanopyOps connects planned GIS geometry,
> offline field execution, evidence completeness, environmental constraints,
> follow-up verification, and a human-approved outcome — into one auditable trail.

A full-stack proof-of-work for **Utility Vegetation Management (UVM)**, built with
the stack the role calls for: **Angular + MapLibre + IndexedDB/PWA** on the front,
**FastAPI + PostgreSQL/PostGIS** on the back.

Installable **offline-first PWA**: an Angular service worker precaches the app
shell and caches read-only API responses (network-first), so the console loads
and shows last-known data with no signal — on top of the IndexedDB outbox
(queued field mutations) and an on-device geofence engine.

**Future Vision.** A cinematic, interactive roadmap at `/vision` (and
[`docs/FUTURE-VISION.md`](docs/FUTURE-VISION.md)) — sensing → AI-ranked risk →
human-signed outcome, over a 0–1 / 1–3 / 3–5-year horizon, with an interactive
"AI copilot explains, a human signs" demo and a species-specific regrowth
predictor. Grounded in public industry sources; AI augments, humans decide.

> **Independent concept. All data is synthetic.** Not affiliated with, or endorsed
> by, The Davey Tree Expert Company. No real utility, worker, location, chemical,
> or client data appears anywhere in this project.

---

## Why this exists

In UVM, risk lives in the gap between *execution* and *outcome*. A span is trimmed
in spring; the biological result — clearance restored, compatible cover
established — isn't visible until weeks later. Post-work **auditing exists precisely
because "done" ≠ "effective,"** and clearance is the outcome regulators check
(NERC FAC-003, state wildfire-mitigation plans). CanopyOps makes that gap visible
and closes it with an exception-first workflow.

It is deliberately **not** another data-collection tool or dashboard — the
differentiator is the assurance layer: evidence-completeness scoring, offline
conflict resolution, temporal verification, and a role-gated, human-approved
outcome.

## The two-minute story (clickable end-to-end)

1. A manager’s plan defines a measurable outcome for a GIS treatment polygon.
2. A field crew records the work **offline**; part of the area is missed and one
   evidence upload fails.
3. The **Sync & Conflict Center** recovers the submission — and when the plan was
   edited server-side, surfaces a **revision conflict** for human resolution.
4. A follow-up visit finds partial regrowth.
5. The reviewer draws **only the geometry needing re-work** and documents the call.
6. The record closes only after plan, execution, evidence, verification, and audit
   history are connected — assembled into a **Proof Pack**.

## Quick start

```bash
# One command — web + api + PostGIS:
docker compose up --build
# → app     http://localhost:8080
# → api     http://localhost:8000/api/health
```

<details>
<summary>Local dev (hot reload)</summary>

```bash
# Database
docker compose up -d db          # PostGIS on host port 5433

# Backend
cd backend
python -m venv .venv && . .venv/Scripts/activate   # (bash: source .venv/bin/activate)
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://canopyops:canopyops@localhost:5433/canopyops
alembic upgrade head && python -m app.seed
uvicorn app.main:app --port 8000

# Frontend (proxies /api → :8000)
cd frontend && npm install && npm start        # http://localhost:4200
```
</details>

**Synthetic logins** (password `canopyops`, or use the in-app role switch):
`manager@` · `crew@` · `reviewer@` · `compliance@` `synthetic.test`

## What’s inside (all verified)

| Module | What it proves |
|---|---|
| **Program Overview** | Executive dashboard blending live record signals with deterministic synthetic trends — plus the **Reliability Outcome** panel: the quantitative form of *closed ≠ effective*. Each circuit's closed work is paired with the indices UVM is judged by (**SAIDI / SAIFI / CAIDI / CMI**); the movement is synthetic but **driven by real record state** (coverage, evidence, verified status), so a circuit that closed work with weak evidence shows little or no SAIDI improvement — surfacing "closed, not effective" |
| **Command Center** | MapLibre GIS map with **switchable basemaps** (real OSM streets / Esri satellite, or an offline synthetic style) + prioritized exception queue + detail, bidirectional selection, URL-persisted filters, backend-driven assurance summary |
| **Field Execution** | Mobile-first capture, coverage control, evidence checklist, **offline save** to IndexedDB |
| **Sync & Conflict Center** | Idempotent sync, **revision-conflict resolution**, failed-upload recovery, connectivity simulation |
| **Outcome Verification** | Evidence-gated verification, targeted follow-up geometry, close → **Proof Pack** with audit trail |
| **Risk Intelligence** | Deterministic, **explainable** span-risk scoring — encroachment · species growth · wildfire/HFTD · terrain slope · outage history — ranked and factor-by-factor transparent, with a **persisted, RBAC-gated human sign-off** (recorded to a review table + the audit trail). Responsible-AI framing: it prioritizes, a certified reviewer decides |
| **Vegetation Intelligence** | Two Davey/DRG UVM concepts made concrete. **Hot-spotting heat**: a MapLibre layer over real corridor centerlines, color + width graduated by each span's reactive-repeat intensity (hazard/elevated priority, reworked plans, ineffective outcomes, low effectiveness) — the reactive work UVM aims to eliminate, with a per-span driver breakdown. **Cycle-buster watchlist**: fast-regrowth species ranked by **days-to-conflict** (a species growth rate projected against remaining MVCD headroom), flagged relative to the trim cycle. Geometry + signals from real records; species/pressures deterministic synthetic |
| **Field Safety · Geofence** | Live protected-zone proximity alerts — PostGIS `ST_Distance`/`ST_Contains` escalate CLEAR → APPROACHING → BREACH as a crew moves; draggable position, patrol simulation, alert log. Server-enforced, and **offline-capable**: a versioned zones snapshot is cached in IndexedDB and a client-side point-in-polygon engine keeps alerts firing with no signal (with an on-device-vs-server parity check) |
| **3D Terrain** | Interactive elevation surface (self-contained canvas renderer — hillshade + hypsometric tint, orbit + vertical exaggeration) with ROW corridors draped and protected zones shaded onto it; a synthetic DEM from the API, plus a corridor **elevation/slope profile** that flags steep sections for access & crew safety |
| **Integration · OData** | SAP-style OData v4 service — treatment plan → **WBS element**, field execution → **CATS** time confirmation; `$metadata`, `$filter/$select/$expand`, deferred navigation, and ETag/304 caching, consumed by an Angular OData client |
| **Quality & Compliance** | The independent **checks-and-balances** QA audit (DRG Work Plan Auditing): a *different* certified reviewer audits a sample of closed work against objective criteria (coverage, evidence, integrity, verification, constraints) computed from the record — the system surfaces the checks, a person signs the verdict (RBAC-gated, append-only, audit-trailed). Plus a **Compliance Evidence Vault**: an auto-assembled per-plan dossier (prescription → execution → evidence integrity → verification → risk sign-off → QA audit → constraints) mapped to **NERC FAC-003 / TVMP / NESC / environmental** requirements with a live completeness score — a filing assembled, not hand-collated |
| **Engineering Evidence** | Test results, architecture, accessibility, perf, and boundaries for a technical reviewer |
| **Compliance Report** | An exportable program rollup (`/report`) — attainment, evidence completeness, NERC/HFTD exposure, and risk governance (distribution + % human-reviewed + unreviewed high/critical), with a ranked span table. **Circuit-scopable**, and exports a real **server-generated PDF** (fixed letterhead) as well as browser print; mirrors a utility compliance dashboard |

## Architecture

```
canopyops/
  frontend/   Angular 18 · MapLibre GL · IndexedDB outbox · Tailwind · CSS motion
  backend/    FastAPI modular monolith · SQLAlchemy 2 + GeoAlchemy2 · Alembic
  db/         PostgreSQL 16 + PostGIS (init: CREATE EXTENSION postgis)
  docker-compose.yml   web + api + db
  .github/workflows/   CI: backend pytest + frontend Jest + build
  docs/       architecture, ADRs, failure map, traceability matrix, demo script
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the system/container/sequence
views, the data model, the state machine, architecture decision records, and the
failure map. See [`docs/INTEGRATION.md`](docs/INTEGRATION.md) for how a utility
integrates it with their own systems (live OpenAPI at `/api/docs`, a
bring-your-own-data GeoJSON import, and the synthetic→real adapter seam).

**Enterprise-integration seam (SAP lingua franca).** A live **OData v4** service at
`/api/odata/` (with EDMX `$metadata`) projects the domain into SAP terms — a
treatment plan is a **WBS element**, a field execution is a **CATS** time
confirmation — and implements server-driven paging, `$filter/$select/$orderby/$expand`,
**deferred navigation**, **ETag/`If-None-Match` (304) caching**, and **`$batch`** —
many reads bundled into one round-trip with `dependsOn` sequencing (`424` when a
predecessor failed; writes return `501` on this read-only facade). The
*Integration · OData* console page consumes it with an app-level ETag cache,
shows the 200-vs-304 revalidation live, and has a `$batch` panel that fires
several reads as a single POST. It is a synthetic, OData-compatible facade — not
a real SAP connection.

### Assurance guarantees (server-enforced, not UI-only)

- **Idempotency** — every mobile mutation carries an `Idempotency-Key`; replays and
  concurrent double-submits return the original record. Zero duplicates.
- **Revision conflict** — a stale offline edit returns `409` with local-vs-server
  revisions for human resolution. Never last-write-wins.
- **Evidence gate** — a failed upload keeps the record incomplete and *blocks*
  verification until recovered.
- **Human-authored outcome** — the API never declares a site effective, safe, or
  compliant. RBAC is enforced on every mutation.

### Scalability & reliability

- **Stateless, horizontally scalable** — a session per request with all shared
  state in Postgres, so `WEB_CONCURRENCY` spreads the API across worker processes
  (and replicas) with no sticky sessions. Uvicorn drains in-flight requests on
  shutdown for zero-drop deploys.
- **Graceful load-shedding** — a bounded in-flight limiter
  (`MAX_CONCURRENT_REQUESTS`) sheds excess load with `503` + `Retry-After` rather
  than letting an unbounded queue turn one overload into a timeout for everyone.
  Liveness/readiness probes stay exempt, so an orchestrator can tell *overloaded*
  from *down*. Live shed count + in-flight are at `GET /api/metrics`.
- **Per-client rate limiting** — a token bucket per client (`RATE_LIMIT_PER_MIN`
  refill, `RATE_LIMIT_BURST` burst) returns `429` + `Retry-After` to a single
  noisy caller, so one client can't monopolise capacity. Distinct from the
  global load-shedder and checked *before* a global slot is taken.
- **Database circuit breaker** — after N consecutive DB connection errors the
  breaker OPENs and DB-backed requests fail fast with `503` instead of each
  waiting for a connection timeout; it HALF-OPENs after a reset window, probes
  once, and closes on success — turning a slow cascading failure into a fast,
  self-healing one.
- **Bounded query time** — every pooled connection carries a Postgres
  `statement_timeout` (default 15s), so a runaway query is cancelled server-side
  instead of pinning a connection.
- **Tuned connection pool** — sized pool + `pool_pre_ping` (survives Postgres
  restarts / idle drops) + periodic recycling; checkout/overflow is live at
  `/api/metrics`.
- **Safe retries by construction** — idempotent mutations + explicit `409`
  conflicts mean a client or load balancer can retry a shed `503` or a transient
  drop with no risk of a duplicate or a silent overwrite.

All observable at the **Engineering Evidence** route (live *System Health* panel)
and covered by `tests/test_reliability.py`.

## Testing

```bash
cd backend && pytest        # 60 passing — idempotency, conflict + resolve, evidence gate, RBAC, coverage,
                            #   full loop, plan creation + validation, overview periods, stewardship, choropleth,
                            #   geo-analyze, OpenAPI contract, GeoJSON import, metrics endpoint, pagination,
                            #   the OData surface ($metadata, $filter w/ grouping, deferred nav, ETag/304),
                            #   geofence proximity alerts (ST_Distance/ST_Contains), offline zones snapshot,
                            #   and 3D terrain (synthetic DEM grid + corridor elevation/slope profile, steep flag)
cd frontend && npm test     # 25 passing — coverage math, status system, component render, chart utilities,
                            #   and the on-device geofence engine (point-in-polygon, distance, escalation,
                            #   MultiPolygon parity with PostGIS)
cd frontend && npm run e2e  # Cypress — 6 passing / 4 specs (critical journey, command palette, risk sign-off, compliance report),
                            #   headless against the running stack
```

Performance: over **1,006 synthetic features**, the server-side bbox spatial filter
returns a bounded subset in **~53 ms** (vs ~380 ms unfiltered).

## Security & responsibility boundaries

Synthetic data only · server-enforced RBAC · opaque evidence storage keys ·
**no** pesticide product/rate/mixing recommendations · **no** AI safety or
compliance verdicts (deterministic rules + human approval) · certification and
label compliance remain human/governance responsibilities.

## Known limitations (stated on purpose)

- Cypress e2e critical journey runs green headless (`npm run e2e`), but is not yet
  wired into the GitHub Actions workflow (that runs pytest + Jest + build).
- The map uses a self-contained synthetic style (no basemap tiles) — deliberate, to
  stay offline-capable and free of external calls.
- All console metrics are synthetic and labeled; no real rework-rate statistics are
  claimed.
- Remote sensing (LiDAR/multispectral) is modeled as an attach-ready data shape, not
  implemented.

## How this maps to the role

See [`docs/TRACEABILITY.md`](docs/TRACEABILITY.md) — each UVM Front-End (and
Full-Stack) requirement mapped to visible product evidence.
