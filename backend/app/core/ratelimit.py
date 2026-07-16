"""Per-client rate limiting (token bucket).

Distinct from the global in-flight limiter (`concurrency.py`): that one protects
the *server* from aggregate overload; this one protects the service from a
*single* noisy client monopolising it. Each client key gets a token bucket that
refills at a steady rate and tolerates a short burst; a request with no token
left is rejected with ``429`` + ``Retry-After``. Thread-safe, with bounded
memory (idle full buckets are evicted). A clock is injectable for tests.
"""
from __future__ import annotations

import math
import threading
import time


class TokenBucket:
    """A classic token bucket: `capacity` tokens, refilled `refill_per_sec`."""

    __slots__ = ("capacity", "refill_per_sec", "tokens", "updated")

    def __init__(self, capacity: float, refill_per_sec: float, now: float) -> None:
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.tokens = capacity
        self.updated = now

    def take(self, now: float) -> tuple[bool, float]:
        """Try to spend one token. Returns (allowed, retry_after_seconds)."""
        # Refill for the elapsed time, capped at capacity.
        elapsed = max(0.0, now - self.updated)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True, 0.0
        # Seconds until one token is available again.
        deficit = 1.0 - self.tokens
        retry = deficit / self.refill_per_sec if self.refill_per_sec > 0 else 60.0
        return False, retry

    def is_full(self, now: float) -> bool:
        elapsed = max(0.0, now - self.updated)
        return min(self.capacity, self.tokens + elapsed * self.refill_per_sec) >= self.capacity


class RateLimiter:
    _MAX_BUCKETS = 10_000  # hard cap on tracked clients (memory bound)

    def __init__(self, capacity: int, refill_per_sec: float, enabled: bool = True) -> None:
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.enabled = enabled and capacity > 0
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self._rejected = 0

    def check(self, key: str, now: float | None = None) -> tuple[bool, float]:
        """Admit (True, 0) or reject (False, retry_after_s) a request for `key`."""
        if not self.enabled:
            return True, 0.0
        now = time.monotonic() if now is None else now
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                if len(self._buckets) >= self._MAX_BUCKETS:
                    self._evict_full(now)
                bucket = TokenBucket(self.capacity, self.refill_per_sec, now)
                self._buckets[key] = bucket
            allowed, retry = bucket.take(now)
            if not allowed:
                self._rejected += 1
            return allowed, retry

    def _evict_full(self, now: float) -> None:
        """Bound memory when the client cap is reached. First drop fully-refilled
        (idle) buckets. If none are full — e.g. a burst of many distinct keys, as
        a forged-header flood would produce — fall back to evicting the
        least-recently-updated buckets so ``_buckets`` can never grow past the cap.
        """
        stale = [k for k, b in self._buckets.items() if b.is_full(now)]
        for k in stale:
            del self._buckets[k]
        if len(self._buckets) >= self._MAX_BUCKETS:
            # Oldest-first eviction of ~10% to amortise the cost across insertions.
            oldest = sorted(self._buckets.items(), key=lambda kv: kv[1].updated)
            for k, _ in oldest[: max(1, self._MAX_BUCKETS // 10)]:
                del self._buckets[k]

    def stats(self) -> dict:
        with self._lock:
            return {
                "tracked_clients": len(self._buckets),
                "rejected_total": self._rejected,
                "capacity": self.capacity,
                "refill_per_min": round(self.refill_per_sec * 60, 1),
                "enabled": self.enabled,
            }


from app.core.config import get_settings  # noqa: E402

_s = get_settings()
rate_limiter = RateLimiter(
    capacity=_s.rate_limit_burst,
    refill_per_sec=_s.rate_limit_per_min / 60.0,
    enabled=_s.rate_limit_enabled,
)
