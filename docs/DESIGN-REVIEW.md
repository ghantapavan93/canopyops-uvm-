# Design Review — a senior read of CanopyOps

*Author's note: this is a self-critique written to raise the bar, not a marketing
doc. It judges the app the way a staff engineer would in a hiring loop: what's
real, what's demo, and what to build next. All data is synthetic; not affiliated
with The Davey Tree Expert Company.*

## 1. Verdict

CanopyOps proves full-stack range and product judgment. The thesis — *a closed
work order proves an activity was recorded, not that the vegetation outcome
occurred* — is sharp and domain-credible, and the plumbing under it is real
(per-tenant RLS, an offline outbox with idempotency + conflict handling, a
durable worker queue, OpenTelemetry).

Where it still reads as a **demo** rather than a **product**:

1. **It's desktop-first for a field tool.** The headline persona is a field crew
   on a phone, yet on mobile the module rail is hidden with *no* replacement —
   you can't navigate. That's the single most important gap.
2. **Everything operates on ~7 records.** No surface has been taken to the scale
   (10k spans) where the interesting engineering lives: virtualization,
   server-side paging, push vs poll.
3. **Breadth over depth.** Fifteen modules in the rail; a reviewer discounts
   breadth and rewards one flow taken to production truth.

The move from here is **depth on one flow**, starting with the field loop.

## 2. Personas and the 30-second job

The console today is one surface for three very different people. Naming their
core task disciplines every design decision:

| Persona | Device | The 30-second job, 20×/day | Today |
| --- | --- | --- | --- |
| Field crew | Phone, gloves, sun, spotty signal | "What's my next span, record what I did, move on" | Works, but no mobile nav; evidence capture is simulated |
| Program manager | Desktop | "Which circuits aren't moving the reliability indices?" | Strong (Overview) |
| Compliance reviewer | Desktop | "Show me the unsigned high/critical spans and let me sign" | Strong (Audit/Report) |

**Implication:** the field crew is the least-served persona and the biggest
differentiator. That's where depth pays off most.

## 3. Trade-offs a reviewer will probe

### 3.1 Polling vs push — RESOLVED: SSE for the Command Center
Every live surface refetched every 12s — O(N clients × polls) for data that
changes rarely. **Decision: SSE for the Command Center; polling stays elsewhere
and as the fallback.** Traffic is one-directional, so SSE beats websockets here.

What the implementation had to get right (each of these is a real trap):
- **The stream carries a signal, not data.** On `treatments.changed` the client
  refetches the page it's showing through the normal filtered/paged/tenant-scoped
  read path — no parallel delta protocol to keep correct.
- **Server-side watermark, cached per program.** Writes come from the API *and*
  the worker (separate containers), so an in-process event bus would miss the
  worker and need Redis to fan out. A cheap watermark query is correct for every
  writer, and caching it per program means N clients cost ONE query per interval.
- **Exempt from the in-flight limiter.** A long-lived stream counted against the
  concurrency cap would let a few open dashboards hold every slot and shed all
  real traffic.
- **Never hold a DB session** for the stream's lifetime — a handful of viewers
  would exhaust the pool. Open a short session per check.
- **Capture the tenant eagerly.** `StreamingResponse` bodies run *after* the
  middleware resets the tenant ContextVar.
- **Bounded connection lifetime.** An endless stream leaves zombies when clients
  vanish without a clean close and pins viewers to one replica; close
  periodically and let the client reconnect.
- **fetch + ReadableStream, not EventSource.** EventSource cannot send headers,
  which would force the JWT into the query string (logged by every proxy).
- **nginx must not buffer** (`proxy_buffering off` + `X-Accel-Buffering: no`) or
  nothing ever reaches the browser.
- **One loop only.** A reconnect loop guarded by a plain `stopped` flag can be
  resurrected by a later `connect()` while it sleeps in backoff, leaving two live
  streams. Browsers allow ~6 connections per origin over HTTP/1.1, so the extras
  starve every XHR. Guarded with a generation counter.

### 3.2 Client-side vs server-side filtering
The Command Center pulls up to 200 rows and filters status **client-side**. Past
200 rows per program the facets under-report silently. This is the clearest
"demo tell." **Fix:** push `status`/`priority`/`q` to the server (the endpoint
already honors them), return a total count, and paginate/virtualize the queue.

### 3.3 Offline blob strategy
The outbox/idempotency/conflict machinery is genuinely good — but evidence
"upload" is simulated. The hard part of offline-first is **binary**: capturing a
photo, buffering it in IndexedDB, respecting storage quota, and resuming the
upload when signal returns. Until that exists, "offline-first" is only half true.

### 3.4 Density vs triage
"Exceptions first" is the promise; the UI shows *everything* first (chips + 6
facets + 4 KPIs + queue + map). A triage tool should open on "here are the 3
things that need you today," with the full grid one click away.

## 4. Prioritized roadmap

**P1 — Field/mobile flow to truth** *(biggest demo→product delta)*
- Mobile module navigation (drawer + hamburger); fix header role-switcher overflow.
- Triage-first queue: lead with the attention set, collapse the rest.
- Real photo capture buffered in IndexedDB with quota handling + resumable sync.

**P2 — Scale the operator surfaces**
- ✅ Total counts (`X-Total-Count`) + honest "showing first N of TOTAL"; server-side
  status filtering for Field Execution and Verification.
- ✅ SSE for the live board, with polling kept as the fallback (see 3.1).
- ⬜ Server-side pagination for the Command Center queue. Blocked on a
  `GET /treatments/stats` endpoint: the KPI cards and status chips are computed
  in the browser over the full loaded set, so paging without server-side facets
  + summary would silently under-report them.
- ⬜ List virtualization (windowing) so 10k rows stay smooth. Needs measured item
  sizing — the queue rows are variable-height (conditional overdue badge and
  constraint chips), so a fixed-size viewport misrenders them.
- ⬜ An Overview "needs you today" focal card ahead of the tables.

**P3 — Product/narrative polish**
- Per-persona entry so each role lands on its 30-second job.
- Empty/error/loading states across every module (Report has one; others don't).
- Separate a visible *demo mode* from the product so RBAC-by-toolbar doesn't read
  as "this is fake."

## 5. What is deliberately good (keep)
- The **thesis** and the SAIDI/SAIFI tie-out — real domain framing.
- **AI is non-decisional** — it explains and ranks; a human signs. Correct posture
  for safety/compliance work.
- **Honesty** — synthetic banners, "not affiliated," no invented integrations.
- The **offline correctness core** (idempotency keys, revision conflicts, RLS).

## 6. How we'll measure "done"
A flow is "true," not "demo," when: it works one-handed on a phone offline, it
holds up at 10k rows, every state (empty/error/loading/conflict) is designed, and
a non-engineer can complete it without help. We build to that bar, one flow at a
time.
