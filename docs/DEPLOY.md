# Deploying CanopyOps

Two supported topologies. Pick deliberately — they are **not** equivalent, and the
free one is a genuine downgrade.

| | Free stack (Vercel + Render + Neon + R2) | One VPS (docker compose) |
| --- | --- | --- |
| Cost | $0 | ~€7/mo all-in |
| Worker | **in-process thread** (degraded) | dedicated container |
| Cold start | none *if* kept warm; ~60s if not | none |
| SSE live board | works while warm; falls back to polling | works |
| Tenant isolation (RLS) | works **only** if the app role is right (below) | works |
| Fidelity to the built architecture | partial | exact |

The research behind this choice — including why every other free tier fails — is
summarised at the bottom.

---

## Option 1 — Free stack

**Angular SPA → Vercel · API → Render (free) · PostGIS → Neon · Evidence → Cloudflare R2**

### 1. Neon (PostGIS + the two-role RLS setup)

Create a Neon project. **That is the whole step — run no SQL by hand.**

Migration `a1e0d2c93b57` creates the postgis extension and `f7a1c2d8e934` creates
the app role, so `alembic upgrade head` against an empty database is sufficient.
(This used to say "first, run `CREATE EXTENSION postgis` in the SQL Editor". It
was a schema dependency living outside the schema chain, held together by someone
reading step 1 carefully — and the first real deploy died on it with
`type "geometry" does not exist`. Locally the extension came from
`db/init/01-postgis.sql` via the postgres image's init hook, which is a *Docker*
mechanism that no managed Postgres has.)

**Do NOT create the app role by hand.** Migration `f7a1c2d8e934` creates it, with
SQL, and explicitly as `NOSUPERUSER NOCREATEDB NOCREATEROLE` — reading the role
name and password **out of `DATABASE_URL`**, which is the only place either is
declared. Set that URL and the role follows from it.

Why that matters: Postgres bypasses row security **unconditionally** for roles
with `SUPERUSER` or `BYPASSRLS` — *even `FORCE ROW LEVEL SECURITY` cannot stop
it*. Neon's `neon_superuser` carries `BYPASSRLS`, and roles created through the
Neon **console/CLI/API inherit it**. Point `DATABASE_URL` at one of those and
every tenant boundary silently disappears **with no error raised** — the demo
looks fine and is wrong. Letting the migration create the role sidesteps this
entirely; creating one yourself in the console would walk straight into it.

Verify after the first deploy (must return `f | f`):

```sql
SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'canopyops_app';
```

**The two URLs.** Both come from Neon's *Connect* dialog. **Turn Connection
pooling OFF for both** — you want the direct host, with no `-pooler` in it.

- `ADMIN_DATABASE_URL` → the **owner** role. Alembic runs DDL, `CREATE ROLE` and
  lock-taking here; that belongs on a direct connection, not through PgBouncer.
- `DATABASE_URL` → user **`canopyops_app`** and **a password you invent**. Same
  host/database as the owner string, different credentials. The migration creates
  the role from these, so whatever you put here *becomes* the role's password —
  there is nothing else to keep in sync.

**Why not the pooler for the app.** The engine sets a server-side
`statement_timeout` through the `options` startup parameter, and Neon's PgBouncer
**rejects `options` outright**: *"unsupported startup parameter in options:
statement_timeout. Please use unpooled connection or remove this parameter."*
Every request 500s while the service still reports healthy.

This doc previously said to use the pooler, reasoning that Neon's free tier is
connection-limited. That was overcautious arithmetic: `DB_POOL_SIZE=3` +
`DB_MAX_OVERFLOW=2` + `WEB_CONCURRENCY=1` is **at most 5 connections**, and
Neon's direct endpoint handles far more. The pooler was solving a problem this
deployment does not have, and the price was `statement_timeout` — a real guard
that stops one runaway query pinning the single free instance.

(The tenant GUC is set with `set_config(..., true)`, i.e. *transaction*-local, so
it *would* survive PgBouncer transaction mode. That part was true — it just
wasn't the constraint that mattered.)

**The password must be strong.** Neon's control plane rejects weak ones, and it
does so at **commit** — every migration appears to run, then the whole
transaction rolls back with `"insecure password, try including more special
characters…"`. Use mixed case, digits and a symbol. **Percent-encode it** for the
URL (`@` → `%40`, `:` → `%3A`, `%` → `%25`); the migration decodes it before
creating the role, so the role gets the real password, not the encoded form.

Rewrite the scheme for SQLAlchemy: `postgresql://` → **`postgresql+psycopg2://`**.
Keep `sslmode=require`. If a connection ever fails on `channel_binding`, drop that
parameter — TLS is already enforced by `sslmode`.

To rotate later: change the password in `DATABASE_URL` and redeploy. The
migration `ALTER`s the existing role to match, so the two cannot drift apart.
(This is why the role and password aren't constants in the migration any more —
they were, and a copy of them being wrong is what broke the first Neon deploy.)

### 2. Evidence storage — you can skip it

`STORAGE_BACKEND=memory` (already set in `render.yaml`). **Three services, not
four.**

Nothing in the demonstration path needs a real bucket. The executions endpoint
writes `EvidenceItem` rows with genuine `STORED` / `FAILED` states, so the golden
record's failed after-photo, the evidence-completeness gate, and the guided sync
recovery all behave exactly as they do locally. Only the presigned
PUT → upload → finalize flow needs object storage, and **no screen in the demo
drives it** — it's covered by tests, and against real MinIO in compose.

If you later want that path live too, add a **Cloudflare R2** bucket (free 10GB,
zero egress) and set `STORAGE_BACKEND=s3` plus `STORAGE_ENDPOINT`
(`https://<account_id>.r2.cloudflarestorage.com`), `STORAGE_ACCESS_KEY`,
`STORAGE_SECRET_KEY`, `STORAGE_BUCKET=evidence`, `STORAGE_REGION=auto`. Give the
bucket a **CORS rule** allowing your Vercel origin with `PUT`/`GET`/`HEAD` —
browsers upload straight to R2, so without CORS it fails in the browser while
working fine from curl. R2 also fixes a real bug the compose setup has: presigned
URLs there point at `minio:9000`, which no real browser can resolve.

### 3. Render (API)

Deploy `render.yaml` as a Blueprint, or create a Docker web service manually with
`dockerfilePath: ./backend/Dockerfile`. Set the `sync: false` env vars from steps
1–2, plus `FRONTEND_ORIGIN` = your Vercel URL.

`RUN_WORKER_IN_PROCESS=true` is set because **Render's free tier has no
background-service type**. The job queue drains on a daemon thread inside the API.
Jobs still run — but this is not the architecture the repo otherwise describes, so
do not claim a dedicated worker container for this deployment.

**Keep it warm — the step that decides the demo.** Render spins a free web service
down after 15 minutes without *inbound* traffic and takes ~1 minute to wake. A
reviewer who opens the link cold watches a spinner for that minute and forms
their opinion there.

`.github/workflows/keepwarm.yml` does this. To arm it, add a repository
**variable** (Settings → Secrets and variables → Actions → **Variables**) named
`API_URL` set to your Render service (**not** the Vercel URL — Vercel never sleeps;
Render is the one that spins down), e.g. `https://canopyops-api.onrender.com`.
Until that variable exists the workflow no-ops rather than failing.

**Do not rely on the GitHub schedule alone.** GitHub throttles scheduled
workflows on free/public repos hard: this one is set to every 10 minutes
(`*/10`) but in practice fires roughly **once an hour**. Render sleeps after 15
minutes idle, so an hourly ping leaves it asleep most of the time and a cold
reviewer still watches the spinner. For a demo that actually stays warm, add a
dedicated free uptime pinger — **cron-job.org** or **UptimeRobot** — hitting
`https://<your-render-service>/api/health` **every 5 minutes**. Those honour the
interval; GitHub's schedule does not. Keep the workflow as harmless backup.

(Render's own cron would be the natural home for it, but Render cron jobs are not
free — a $0 deploy would either be rejected or quietly start charging.)

Render grants 750 free instance-hours/month; kept warm 24/7 a single service uses
~730 — it fits, but it is the *whole* allowance, so don't run a second free
service beside it.

### 4. Vercel (SPA)

Import the repo, then set two things in the import screen and nothing else:

- **Root Directory → `frontend`**. Left at the repo root, Vercel never finds
  `vercel.json`, so every rewrite is ignored: the build goes green and each API
  call 404s.
- **Application Preset → `Other`**. Vercel auto-detects Angular and the preset
  imposes its own output directory. `vercel.json` declares `"framework": null`
  and should override it, but when it doesn't you get `404: NOT_FOUND` on a
  successful build, which reads like a routing bug rather than a config clash.

Leave Build/Output Settings and Environment Variables empty — `vercel.json`
supplies the build, and the SPA needs no env vars.

**Edit the rewrite destination** in `frontend/vercel.json` to your real Render URL.

**What `vercel.json` does, and why** (the file itself carries no comments — Vercel
validates it against a strict schema with `additionalProperties: false`, so a
`"comment"` key is rejected outright with *"should NOT have additional property
`comment`"*. JSON has no comments; faking them with a key breaks the deploy):

- **`/api/:path*` → Render.** The SPA's `apiBase` is the relative `/api`, so the
  browser only ever talks to the Vercel origin and **no CORS is involved** in
  normal calls. This rewrite is declared *first*.
- **`/((?!api/).*)` → `/index.html`.** SPA fallback for Angular's client-side
  routes. The negative lookahead and the ordering both matter: without them this
  rule swallows the API calls.
- **`Cache-Control: no-cache` on `ngsw-worker.js` / `ngsw.json` / the manifest.**
  The service worker and its manifest must never be cached aggressively or
  clients pin themselves to a stale bundle — a browser can then keep serving an
  old build long after a deploy, which looks exactly like the deploy failing.
- **`nosniff` / `DENY` / `strict-origin-when-cross-origin`** on everything.

### Known degradations (say these out loud, don't discover them)

1. **Worker is in-process.** Dies with the web process; cannot scale separately.
2. **SSE pushes — Vercel does *not* buffer it.** Measured against the live
   deployment: `curl -N https://<your-app>.vercel.app/api/events/stream` returns
   `event: hello` immediately, then `: keepalive`. So the "Live" chip reads
   `push`. This entry used to hedge that the rewrite proxy *might* buffer
   `text/event-stream` and the client would fall back to polling; that was a
   guess, and it was wrong. (A `poll` reading in an embedded preview pane is the
   pane intercepting the stream, not this stack.)

   The remaining real risk is Render's 15-minute *inbound*-traffic reaper: SSE
   keepalives are outbound and do not reset it, so a stream can outlive the
   instance that serves it. The keep-warm ping is what prevents that. The client
   falls back to polling on its own if the stream dies.
3. **Cold start** if the pinger stops.
4. Vercel Hobby is **non-commercial only** — fine for a portfolio piece.

---

## Option 2 — One VPS (recommended once it matters)

Any small box (~€7/mo all-in). Everything you built runs **unchanged**: dedicated
worker container, MinIO, PostGIS, two-role RLS with a real superuser, SSE with no
spin-down and no proxy buffering.

```bash
git clone <repo> && cd canopyops
# set real secrets — never ship the defaults
export JWT_SECRET=$(openssl rand -hex 32)
export FRONTEND_ORIGIN=https://your.domain
docker compose up -d
docker compose exec api python -m app.seed
```

Put Caddy in front for automatic Let's Encrypt TLS (compose serves plain `:80`).
Fix before exposing publicly: `STORAGE_ENDPOINT` must be a browser-reachable
hostname, not `minio:9000`.

---

## Why not the other free tiers (verified 2026-07)

- **Render Postgres** — free instances **expire 30 days after creation**. Worse
  than a cold start: the link hits a dead database. (Hence Neon.)
- **Koyeb** — free instances *"can't be used as Worker Services"* (a prohibition on
  service *type*), and free Postgres is capped at **5 hours of active time/month**;
  a continuously-polling worker burns that in ~5 hours and the DB is dead for the
  other ~715.
- **Supabase** — free projects **pause after ~7 days idle** → dead demo link.
  (PostGIS and `CREATE ROLE` are both fine; the pause is the killer.)
- **Railway** — always-on by default and a genuinely good fit, but **no free tier**.
- **Oracle Cloud Always Free** — *unevaluated*. Could plausibly run the whole
  compose stack for €0; the counterweight is documented reclamation of idle
  instances. Worth checking before paying for a VPS.

Sources: [Render free](https://render.com/docs/free) · [Koyeb instances](https://www.koyeb.com/docs/reference/instances) ·
[Railway app sleeping](https://docs.railway.com/reference/app-sleeping) · [Neon roles](https://neon.com/docs/manage/roles) ·
[Postgres RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) · [Hetzner pricing](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/)
