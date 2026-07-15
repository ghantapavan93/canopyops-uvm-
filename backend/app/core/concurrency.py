"""Graceful overload protection.

A bounded in-flight limiter: when more than ``max_concurrent`` requests are
being handled at once, further requests are shed immediately with ``503`` +
``Retry-After`` instead of piling onto the event loop and exhausting the
connection pool. Shedding early keeps latency bounded for the requests already
admitted — a queue that grows without limit just converts an overload into a
timeout for *everyone*. Thread-safe; ``max_concurrent = 0`` disables the cap.
"""
from __future__ import annotations

import threading


class InFlightLimiter:
    def __init__(self, max_concurrent: int) -> None:
        self.max = max(0, int(max_concurrent))
        self._n = 0
        self._peak = 0
        self._shed = 0
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        """Admit the request (True) or shed it (False) if at capacity."""
        with self._lock:
            if self.max and self._n >= self.max:
                self._shed += 1
                return False
            self._n += 1
            if self._n > self._peak:
                self._peak = self._n
            return True

    def release(self) -> None:
        with self._lock:
            if self._n > 0:
                self._n -= 1

    def stats(self) -> dict:
        with self._lock:
            return {
                "in_flight": self._n,
                "peak": self._peak,
                "shed_total": self._shed,
                "limit": self.max,
            }


from app.core.config import get_settings  # noqa: E402

limiter = InFlightLimiter(get_settings().max_concurrent_requests)
