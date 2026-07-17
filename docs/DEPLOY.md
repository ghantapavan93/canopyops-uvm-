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

Create a Neon project, then in the SQL Editor:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

**Do NOT create the app role by hand.** Migration `f7a1c2d8e934` creates it, with
SQL, and explicitly as `NOSUPERUSER NOCREATEDB NOCREATEROLE`:

```sql
CREATE ROLE canopyops_app LOGIN PASSWORD 'canopyops_app' NOSUPERUSER NOCREATEDB NOCREATEROLE;
```

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

**The two URLs.** Both come from Neon's *Connect* dialog; note the pooling toggle:

- `ADMIN_DATABASE_URL` → the **owner** role, **Connection pooling OFF** (the
  direct endpoint, no `-pooler` in the host). Alembic runs DDL, `CREATE ROLE` and
  lock-taking here; that belongs on a direct connection, not through PgBouncer.
- `DATABASE_URL` → **`canopyops_app` / `canopyops_app`**, **pooling ON** (the
  `-pooler` host). Same host/database as the owner string, different credentials.
  Pooling is right for the app: Neon's free tier is connection-limited, and the
  tenant GUC is set with `set_config(..., true)` — *transaction*-local, which is
  exactly what survives PgBouncer's transaction mode.

Rewrite the scheme for SQLAlchemy: `postgresql://` → **`postgresql+psycopg2://`**.
Keep `sslmode=require`. If a connection ever fails on `channel_binding`, drop that
parameter — TLS is already enforced by `sslmode`.

The app-role password is the synthetic `canopyops_app` and is public in this repo.
That is acceptable here because the data is synthetic and RLS is fail-closed (with
no `app.tenant_id` set, a direct connection reads **zero** rows). For hygiene you
can rotate it after the first deploy — `ALTER ROLE canopyops_app PASSWORD '…'` —
and update `DATABASE_URL`.

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

`.github/workflows/keepwarm.yml` already does this. To arm it, add a repository
**variable** (Settings → Secrets and variables → Actions → **Variables**) named
`API_URL` set to your Render service, e.g. `https://canopyops-api.onrender.com`.
Until that variable exists the workflow no-ops rather than failing.

(Render's own cron would be the natural home for it, but Render cron jobs are not
free — a $0 deploy would either be rejected or quietly start charging.)

Render grants 750 free instance-hours/month; kept warm 24/7 a single service uses
~730 — it fits, but it is the *whole* allowance, so don't run a second free
service beside it.

### 4. Vercel (SPA)

Import the repo with **root directory `frontend/`**. `vercel.json` already sets the
build, output dir (`dist/frontend/browser`), SPA fallback, and a `/api/*` rewrite
to Render — the rewrite is why the SPA keeps its relative `apiBase` and needs no
CORS for normal calls.

**Edit the rewrite destination** in `frontend/vercel.json` to your real Render URL.

### Known degradations (say these out loud, don't discover them)

1. **Worker is in-process.** Dies with the web process; cannot scale separately.
2. **SSE may fall back to polling.** Two independent risks: Render's 15-min
   *inbound*-traffic reaper (server keepalives are outbound and don't reset it),
   and Vercel's rewrite proxy possibly buffering `text/event-stream`. The client
   detects this and falls back to polling automatically — the "Live" chip reads
   `poll` instead of `push`. Verify with:
   `curl -N https://<your-app>.vercel.app/api/events/stream` — a `hello` frame
   should arrive immediately. If it hangs, the proxy is buffering.
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
