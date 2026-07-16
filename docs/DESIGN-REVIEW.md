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

### 3.1 Polling vs push
Every live surface refetches every 12s and renders "updated Ns ago." Simple and
robust, but O(N clients × polls) of load for data that changes rarely.
- **Keep polling** if the story is "operational simplicity, no stateful fan-out."
- **Move to SSE** (one-way server→client) if the story is "live ops board." SSE
  fits this app better than websockets — traffic is one-directional and SSE
  survives proxies/reconnects cheaply.
- **Decision:** defensible either way; the failure is not having an answer.
  Recommend SSE for the Command Center only, polling elsewhere.

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
- Server-side pagination + filtering for the Command Center queue; total counts.
- List virtualization (windowing) so 10k rows stay smooth.
- SSE for the live board; keep polling as the fallback.
- An Overview "needs you today" focal card ahead of the tables.

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
