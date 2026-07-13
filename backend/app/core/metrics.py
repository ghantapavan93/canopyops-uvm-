"""In-process request metrics — a lightweight observability layer so an ops team
can see request volume, error rate, and latency percentiles per endpoint without
an external APM. Thread-safe; bounded memory (latency samples are capped)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * p))
    return round(ordered[idx], 1)


class Metrics:
    _SAMPLE_CAP = 500  # keep last N latencies per endpoint

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started = time.time()
        self._total = 0
        self._errors = 0
        self._by_endpoint: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "errors": 0, "latencies": []}
        )

    def record(self, endpoint: str, status: int, duration_ms: float) -> None:
        with self._lock:
            self._total += 1
            is_error = status >= 500
            if is_error:
                self._errors += 1
            e = self._by_endpoint[endpoint]
            e["count"] += 1
            if is_error:
                e["errors"] += 1
            e["latencies"].append(duration_ms)
            if len(e["latencies"]) > self._SAMPLE_CAP:
                e["latencies"] = e["latencies"][-self._SAMPLE_CAP :]

    def snapshot(self) -> dict:
        with self._lock:
            all_latencies = [
                lat for e in self._by_endpoint.values() for lat in e["latencies"]
            ]
            endpoints = [
                {
                    "endpoint": name,
                    "count": e["count"],
                    "errors": e["errors"],
                    "p50_ms": _percentile(e["latencies"], 0.50),
                    "p95_ms": _percentile(e["latencies"], 0.95),
                }
                for name, e in sorted(
                    self._by_endpoint.items(), key=lambda kv: -kv[1]["count"]
                )
            ]
            return {
                "uptime_s": round(time.time() - self._started, 1),
                "total_requests": self._total,
                "errors": self._errors,
                "error_rate": round(self._errors / self._total, 4) if self._total else 0.0,
                "latency_ms": {
                    "p50": _percentile(all_latencies, 0.50),
                    "p95": _percentile(all_latencies, 0.95),
                    "p99": _percentile(all_latencies, 0.99),
                },
                "endpoints": endpoints[:15],
            }


metrics = Metrics()
