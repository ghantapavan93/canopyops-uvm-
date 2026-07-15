# Operations runbook

Operational recovery for CanopyOps. Targets are **design targets** for a
prototype; they define intended behavior and the procedures to meet them — they
are not a claim of a measured production SLA.

## Service objectives

| Objective | Target |
|---|---|
| API availability (design) | 99.9% |
| Recovery Point Objective (RPO) | ≤ 5 min (max acceptable data loss) |
| Recovery Time Objective (RTO) | ≤ 30 min (max acceptable downtime) |

See [`SLO.md`](./SLO.md) for latency/error SLOs and [`LOAD-TEST.md`](./LOAD-TEST.md)
for measured performance.

## Components & health

| Component | Health signal |
|---|---|
| API (`api`) | `GET /api/health` (liveness), `GET /api/ready` (DB + PostGIS) |
| Worker (`worker`) | logs `worker_started`; job rows move `queued → running → succeeded` |
| Postgres/PostGIS (`db`) | `pg_isready`; `/api/ready` runs `SELECT PostGIS_Version()` |
| Object storage (`minio`) | `:9000/minio/health/live` |
| Observability | `/api/metrics` (rate/error/latency, pool, breaker, rate-limit), `/api/metrics/prometheus`, OTel traces (`X-Trace-Id`) |

## Backups

- **Postgres**: nightly `pg_dump` + WAL archiving for point-in-time recovery
  (PITR) → RPO ≤ 5 min. Restore: provision a fresh `db`, `pg_restore` the base
  backup, replay WAL to the target timestamp.
- **Object storage (evidence)**: bucket versioning + cross-region replication in
  production; evidence objects are immutable once finalized (checksum recorded).
- **App state is disposable**: the API and worker are stateless — all durable
  state is Postgres + object storage. Recovery = restore those two.

> Prototype note: backups/PITR are documented procedures, not yet automated in
> the compose demo (which uses a local volume).

## Runbooks

### DB is down / browning out
1. Alert source: `/api/ready` failing; the **DB circuit breaker** opens and
   DB-backed requests fast-fail `503` (they don't hang) — confirm at
   `/api/metrics` → `db_circuit.state = open`.
2. Check `db` container / managed instance; restore from backup if unrecoverable
   (see Backups → RTO ≤ 30 min).
3. On recovery the breaker half-opens, probes, and closes automatically; no API
   redeploy needed (`pool_pre_ping` re-establishes connections).

### Latency / error-rate spike
1. `/api/metrics`: check `error_rate`, `latency_ms` p95/p99, `concurrency`
   (load-shed count), `rate_limit` (429s), pool checkout.
2. If overload: the in-flight limiter sheds `503` and the per-client limiter
   `429`s abusive clients automatically. Scale out via `WEB_CONCURRENCY` /
   replicas (the API is stateless, no sticky sessions).
3. Pull the trace for a slow request by `X-Trace-Id` (request → DB spans) to find
   the offending query; review its plan with `EXPLAIN ANALYZE`.

### Job queue backing up
1. `GET /api/jobs`: are jobs stuck `running` or piling up `queued`?
2. Worker crash-safe: it processes jobs with `FOR UPDATE SKIP LOCKED`; a dead
   worker's claimed job is retried after its lock releases. Scale workers
   horizontally (add `worker` replicas) — no coordination needed.
3. A repeatedly-failing job retries with backoff then lands terminal `failed`
   with its `error`; inspect and re-enqueue after fixing the cause.

### Deploy / rollback
1. Deploy is rolling: uvicorn drains in-flight requests on `SIGTERM`
   (`--timeout-graceful-shutdown`).
2. DB migrations run on API start (`alembic upgrade head`); migrations are
   additive/backward-compatible so an old and new API can briefly coexist.
3. Rollback = redeploy the previous image; if a migration must be reverted, use
   the Alembic `downgrade` for that revision.

## Escalation
Correlate everything by `correlation_id` (logs) and `trace_id` (OTel). A
user-reported failure carries an `X-Trace-Id` and a `correlation_id` in the error
envelope — quote either to jump straight to the request's logs and trace.
