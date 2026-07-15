"""Dependency-free load test — a fallback when k6 isn't installed.

Fires N requests per endpoint at a fixed concurrency against the running API and
reports p50/p95/p99 latency, throughput, and error rate. Produces the numbers
published in docs/LOAD-TEST.md. Run against the load-test compose overlay (rate
limit lifted) so we measure server latency, not the per-client limiter.

    python load/run_load.py --base http://localhost:8001/api --requests 2000 --concurrency 50
"""
from __future__ import annotations

import argparse
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ENDPOINTS = [
    ("health", "/health"),
    ("overview", "/overview"),
    ("risk", "/risk/spans"),
    ("vault", "/vault"),
    ("odata_wbs", "/odata/WbsElements?$top=5&$count=true"),
]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1))))
    return ordered[idx]


def _hit(url: str) -> tuple[float, int]:
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:  # noqa: PERF203
        status = e.code
    except Exception:  # noqa: BLE001
        status = 0
    return (time.perf_counter() - start) * 1000.0, status


def run(base: str, name: str, path: str, requests: int, concurrency: int) -> dict:
    url = base + path
    latencies: list[float] = []
    errors = 0
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for ms, status in pool.map(lambda _: _hit(url), range(requests)):
            latencies.append(ms)
            if status == 0 or status >= 500:
                errors += 1
    wall = time.perf_counter() - t0
    return {
        "endpoint": name,
        "n": requests,
        "rps": round(requests / wall, 1),
        "p50": round(_percentile(latencies, 50), 1),
        "p95": round(_percentile(latencies, 95), 1),
        "p99": round(_percentile(latencies, 99), 1),
        "max": round(max(latencies), 1),
        "err_pct": round(errors / requests * 100, 2),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001/api")
    ap.add_argument("--requests", type=int, default=2000)
    ap.add_argument("--concurrency", type=int, default=50)
    args = ap.parse_args()

    print(f"base={args.base} requests={args.requests} concurrency={args.concurrency}\n")
    print("| endpoint | reqs | rps | p50 ms | p95 ms | p99 ms | max ms | err% |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for name, path in ENDPOINTS:
        r = run(args.base, name, path, args.requests, args.concurrency)
        print(f"| `{r['endpoint']}` | {r['n']} | {r['rps']} | {r['p50']} | "
              f"{r['p95']} | {r['p99']} | {r['max']} | {r['err_pct']} |")


if __name__ == "__main__":
    main()
