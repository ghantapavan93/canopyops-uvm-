# Demo click-through script

An interviewer-ready walkthrough. There are two paths:

- **Core loop (~3 min)** — the flagship "closed ≠ effective" story, plan → verified
  proof. Do this one if you have limited time.
- **Differentiator tour (~4 min more)** — the geospatial + integration depth that
  maps to the UVM Angular/full-stack role (geofencing, 3D terrain, SAP-style OData,
  offline PWA).

> Independent concept. All data is synthetic. Not affiliated with, or endorsed by,
> The Davey Tree Expert Company.

---

## 0. Setup (before the call)

```bash
docker compose up --build -d          # web + api + db
# app  → http://localhost:8080
# api  → http://localhost:8000/api/health   (docs at /api/docs)
```

- Open **http://localhost:8080** and keep it there. **Navigate with the in-app
  left menu and the header role switch — not the browser URL bar** — so the
  simulated-offline state survives between screens.
- **Roles** switch instantly from the header (top-right): **Manager · Field crew ·
  Reviewer · Compliance**. RBAC is enforced server-side, not just hidden in the UI.
- **Reset to a clean demo state** anytime:
  ```bash
  docker compose exec api python -m app.seed
  ```

---

## Core loop (~3 minutes)

### 0:00 — The hook (Landing)
Land on **http://localhost:8080**.
> "A closed work order proves an activity was *recorded*. It doesn't prove the
> vegetation *outcome* occurred."

Scroll to **"Inside the console"** — six module cards. Click **Open console →**.

### 0:20 — Command Center (Manager)
Left nav → **Command Center**.
- "Exceptions first." Point out the **prioritized queue** (hazard / overdue float
  to the top), the **assurance summary** strip (evidence incomplete, constraint
  intersects, verification overdue), and **map ⇄ queue** bidirectional selection.
- Filters + selection live in the **URL** — a shareable review link.
- Top-right of the map: the **basemap switcher** — flip **Synthetic → Streets →
  Satellite** (the synthetic sandbox sits at real coordinates near Dublin, Ohio,
  so real imagery shows real streets under the operational layers).

### 0:45 — Field Execution, offline (Field crew)
Header role → **Field crew**. Left nav → **Field Execution**.
- Toggle connectivity **Off**. Pick a work order.
- Drag coverage to ~**60%** (or the **75%** preset) — "partial coverage."
- On **photo after**, tick **simulate upload failure**. Watch the live **evidence
  meter** drop to **2/3 · 67% · "verification blocked."**
- **Record execution (save offline)**.
> "No signal, no data loss — it's queued in the IndexedDB outbox."

### 1:15 — Sync & Conflict Center
Left nav → **Sync & Conflict**.
- Click **⚡ Simulate concurrent edit** (a manager edited the plan on another
  device). Toggle connectivity **On** → **Sync now**.
- The item goes to **Conflict** — *your revision 1 vs server revision 2*. Click
  **Adopt server revision & re-apply.** "Never last-write-wins."
- The synced record shows a failed photo. Click the failed evidence chip to
  **retry** it → evidence goes **100% complete**. "A failed upload can't fake done."
- (Optional) Click **Inspect payload** on a row — the exact `POST /api/executions`
  body and the **Idempotency-Key** that makes retries safe.

### 1:50 — Outcome Verification (Reviewer)
Header role → **Reviewer**. Left nav → **Outcome Verification**.
- Filter chips: **Awaiting**. Open the record. If evidence were incomplete,
  verification is **blocked** (the gate).
- Pick **Partially effective**, toggle **Regrowth observed** — watch the live
  **"Will record"** summary update. Draw the **targeted follow-up** on the map:
  "only the area needing another pass, not a blind full-corridor repeat."
- **Record verification** → **Plan targeted follow-up** → **Close record & build
  Proof Pack.**

### 2:30 — Proof Pack + close
The closed record assembles a **Proof Pack**: outcome, coverage, evidence, and the
full **audit trail** (`execution.submitted → plan.verified → plan.followup_planned
→ plan.closed`).
> "Plan to verified outcome — offline-safe, conflict-aware, and defensible line by
> line. Closed is not the same as effective, and the system won't let you pretend
> it is."

---

## Differentiator tour (~4 minutes)

### Program Overview — live, real-data
Left nav → **Program Overview**.
- The **Treatment lifecycle** bar and **Recent activity** feed are computed from
  real DB state (a `SELECT … GROUP BY status` and the immutable audit trail) — not
  synthetic curves. **Work-plan attainment** reads *"Live: N of M plans executed."*
- **Live** toggle + **↻ updated Ns ago** — it re-reads on a cadence. Click a
  lifecycle segment → it deep-links into the Command Center filtered to that status.
- The macro tiles (MVCD, SAIDI, spend) are clearly labeled **⚠ Synthetic**.

### Field Safety · Geofencing
Left nav → **Field Safety · Geofence**.
- Click **▶ Simulate patrol** — the crew walks toward the water buffer and the
  banner escalates **CLEAR → APPROACHING → BREACH** ("STOP — inside a no-work
  zone"), logging each transition. Distances/containment are computed **server-side
  with PostGIS**.
- Now click the **Online** pill to go **Offline** and run the patrol again — the
  telemetry flips to **"computed on-device · cached zones"** and it *still* fires
  alerts, matching the server (an on-device point-in-polygon engine + an IndexedDB
  zone snapshot). "The safety logic isn't UI-only, and it survives lost signal."

### 3D Terrain awareness
Left nav → **3D Terrain**.
- Drag to **orbit** the shaded surface; nudge **vertical exaggeration**; toggle
  **Protected zones** (shaded onto the terrain) and **Wireframe**.
- The profile panel defaults to **CKT-8848 · RIDGE CROSSING**: **42.6% max slope,
  2 steep sections → "plan access & fall protection."** Corridors are draped on the
  terrain. (Self-contained canvas renderer — no basemap tiles needed.)

### Integration · OData (the SAP seam)
Left nav → **Integration · OData**.
- "This is the seam an Angular⇄SAP shop lives in." A treatment plan projects to a
  **WBS element**; a field execution to **CATS** time confirmations.
- Click a **$filter** chip and change **$orderby** — server-driven. Hit **↻
  Refetch**: the telemetry shows **304 · revalidated (served from cache)** — ETag
  conditional caching. Click **▸ $expand** on a row: CATS entries load **only then**
  (deferred navigation). Open **$metadata** for the EDMX contract.

### Engineering Evidence + install as an app
Left nav → **Engineering Evidence**.
- The scoreboard: **43 backend (pytest) · 25 frontend (Jest) · 1 Cypress journey**;
  a **live system-health** panel (in-process metrics, p50/p95/p99); the OpenAPI
  contract link; and an **honest** known-limitations list.
- In Chrome/Edge, the browser offers **Install** (it's an offline-first PWA — a
  service worker precaches the app shell and read-only API responses). Install it,
  turn off Wi-Fi, reopen — the console still loads with last-known data.

---

## Talking points that map to the role

- **Angular ⇄ integration:** signals + RxJS + reactive forms; and an **OData v4**
  layer mapping the domain to **WBS/CATS** — the SAP lingua franca — with deferred
  loading and ETag caching (the exact "OData performance" work the role calls for).
- **Full-stack data orchestration:** typed contracts (OpenAPI), server-enforced
  RBAC, idempotency, revision conflicts, PostGIS spatial math.
- **Quality engineering:** 43 + 25 unit/integration tests, a Cypress critical
  journey, structured logging + an in-process metrics registry for triage.
- **Offline-first field reality:** three complementary layers — IndexedDB outbox,
  on-device geofence engine, and a service-worker app-shell/API cache.

## Honest boundaries (say them — they build trust)
Synthetic data only · no real SAP/LiDAR/GPS (adapter seams shown) · deterministic
rules + **human-authored** outcomes, no AI verdicts · JWT dev secret · maps need a
real browser (WebGL) to render tiles.
