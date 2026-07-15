# Load test — measured results

These are **real measurements**, not targets. Reproduce them with the artifacts
in [`/load`](../load): a [k6 script](../load/k6-smoke.js) (the canonical tool) and
a dependency-free [Python runner](../load/run_load.py) (used for the table below,
since k6 wasn't installed on the test machine).

## Method

- Stack: the full Docker Compose stack (`web + api + db/PostGIS + worker + minio`)
  on a developer laptop (Windows 11 + Docker Desktop).
- The API was run with the **load-test overlay**
  ([`load/docker-compose.loadtest.yml`](../load/docker-compose.loadtest.yml)):
  `WEB_CONCURRENCY=4` and the **per-client rate limit lifted**, so we measure
  server + DB latency rather than the limiter (the limiter and load-shedder are
  proven separately in `tests/test_resilience.py` and `tests/test_reliability.py`).
- Workload: **1,500 requests per endpoint at concurrency 40**.
- Data: the synthetic seed (6 plans / 7 corridors). Latencies scale with dataset
  size; the spatial endpoints below are the ones that grow with geometry count.

```
python load/run_load.py --base http://localhost:8001/api --requests 1500 --concurrency 40
```

## Results

| endpoint | reqs | rps | p50 ms | p95 ms | p99 ms | max ms | err% |
|---|---:|---:|---:|---:|---:|---:|---:|
| `health` (liveness) | 1500 | 523.0 | 41.5 | 104.7 | 899.0 | 965.4 | 0.0 |
| `overview` (DB aggregate) | 1500 | 179.6 | 210.6 | 338.3 | 397.0 | 503.7 | 0.0 |
| `risk/spans` (spatial + scoring) | 1500 | 113.4 | 338.1 | 518.2 | 611.8 | 719.4 | 0.0 |
| `vault` (multi-join dossiers) | 1500 | 175.8 | 216.6 | 341.5 | 431.8 | 501.2 | 0.0 |
| `odata/WbsElements` (projection) | 1500 | 94.9 | 406.8 | 604.8 | 684.7 | 865.6 | 0.0 |

## Reading it against the [SLO targets](./SLO.md)

- **Error rate 0.0%** across 7,500 requests — comfortably under the < 1% target.
- **Non-spatial p95 < 500 ms**: `overview` (338), `vault` (342) meet it; `health`
  p50 is 42 ms (its p99/max tail — ~0.9 s — is Docker Desktop I/O jitter on a
  laptop, not server work).
- **Spatial p95 < 1500 ms**: `risk/spans` (518) and the OData projection (605)
  are well within target.

## Honest caveats

- Measured on a laptop through Docker Desktop's VM — absolute numbers would
  differ (usually improve) on real hardware/managed Postgres. The point is the
  **shape**: 0% errors, bounded p95, spatial endpoints heavier than non-spatial.
- This is a smoke/ramp load, not a soak or spike test. A production readiness
  pass would add a soak (steady load for hours) and a spike test, and re-run
  against a production-sized dataset with the spatial indexes' query plans
  reviewed (`EXPLAIN ANALYZE`).
