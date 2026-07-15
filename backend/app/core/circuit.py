"""Circuit breaker for the database dependency.

When Postgres is browning out, every request that waits for a connection times
out slowly — the worst failure mode, because latency climbs and the pool drains
while clients pile up. A circuit breaker converts that into a *fast* failure:
after `failure_threshold` consecutive DB errors it OPENS and rejects DB-backed
requests immediately with `503`, sparing them the timeout. After
`reset_timeout_s` it goes HALF_OPEN and lets a single probe through; a success
CLOSES it, a failure re-OPENS it. Thread-safe; clock injectable for tests.
"""
from __future__ import annotations

import threading
import time

CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int, reset_timeout_s: float, enabled: bool = True) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.reset_timeout_s = reset_timeout_s
        self.enabled = enabled
        self._state = CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._trips = 0
        self._lock = threading.Lock()

    def allow(self, now: float | None = None) -> bool:
        """May a request proceed? OPEN fails fast until the reset window elapses,
        then a single HALF_OPEN probe is admitted."""
        if not self.enabled:
            return True
        now = time.monotonic() if now is None else now
        with self._lock:
            if self._state == OPEN and (now - self._opened_at) >= self.reset_timeout_s:
                self._state = HALF_OPEN  # admit one probe
            return self._state != OPEN

    def record_success(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._failures = 0
            if self._state != CLOSED:
                self._state = CLOSED

    def record_failure(self, now: float | None = None) -> None:
        if not self.enabled:
            return
        now = time.monotonic() if now is None else now
        with self._lock:
            self._failures += 1
            # A failed probe (HALF_OPEN) re-opens immediately; otherwise open once
            # the consecutive-failure threshold is crossed.
            if self._state == HALF_OPEN or self._failures >= self.failure_threshold:
                if self._state != OPEN:
                    self._trips += 1
                self._state = OPEN
                self._opened_at = now

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def stats(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "consecutive_failures": self._failures,
                "trips_total": self._trips,
                "failure_threshold": self.failure_threshold,
                "reset_timeout_s": self.reset_timeout_s,
                "enabled": self.enabled,
            }


from app.core.config import get_settings  # noqa: E402

_s = get_settings()
db_breaker = CircuitBreaker(
    failure_threshold=_s.db_breaker_failure_threshold,
    reset_timeout_s=_s.db_breaker_reset_timeout_s,
    enabled=_s.db_breaker_enabled,
)
