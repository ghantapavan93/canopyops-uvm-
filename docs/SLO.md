# Service-level objectives (design targets)

These are **design targets** the system is built and tested against — not a
claimed production SLA. Measured performance lives in
[`LOAD-TEST.md`](./LOAD-TEST.md); operational recovery in
[`RUNBOOK.md`](./RUNBOOK.md).

## Latency & correctness

| SLO | Target | How it's checked |
|---|---|---|
| Non-spatial API p95 | < 500 ms | k6 / `run_load.py` thresholds; `/api/metrics` p95 |
| Common spatial-query p95 | < 1500 ms | same, tagged `spatial` |
| Error rate | < 1% (5xx) | load test + `/api/metrics` `error_rate` |
| No duplicate state-changing ops from retries | 0 | `Idempotency-Key` (`test_api`) |
| Offline records survive refresh/restart | 100% | IndexedDB outbox (critical-journey e2e) |
| Core workflow keyboard-accessible | yes | practice + axe gate (`ACCESSIBILITY.md`) |
| No serious/critical a11y violations | 0 | axe-core CI gate |

Measured (laptop / Docker Desktop, rate limit lifted): non-spatial p95 338–342 ms,
spatial p95 518–605 ms, **0% errors** over 7,500 requests. See `LOAD-TEST.md`.

## Availability & recovery

| SLO | Target |
|---|---|
| API availability (design) | 99.9% |
| RPO (max data loss) | ≤ 5 min |
| RTO (max downtime) | ≤ 30 min |

## Error budget & alerting (intended)

- Error budget: 0.1% unavailability/month (~43 min) at 99.9%.
- Alert when, over 5 min: `error_rate > 1%`, non-spatial p95 > 500 ms, spatial
  p95 > 1500 ms, `db_circuit.state = open`, or `queued` jobs climbing.
- All signals are already exported: `/api/metrics` (+ Prometheus text format) and
  OpenTelemetry traces; wire a Prometheus/Grafana + OTLP collector to alert.

## Explicitly out of scope for the prototype

Soak/spike load profiles, multi-region failover, automated backup/PITR, and a
production-sized dataset with reviewed spatial query plans (`EXPLAIN ANALYZE`).
These are named as the next readiness steps, not claimed as done.
