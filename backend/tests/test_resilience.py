"""Per-client rate limiting (token bucket) and the database circuit breaker.
Both use an injectable clock so the time-based behaviour is deterministic."""
from __future__ import annotations

from app.core.circuit import CLOSED, HALF_OPEN, OPEN, CircuitBreaker, db_breaker
from app.core.ratelimit import RateLimiter


# --- token-bucket rate limiter -------------------------------------------------
def test_token_bucket_bursts_then_throttles_then_refills():
    # capacity 3, refills 1 token/sec
    rl = RateLimiter(capacity=3, refill_per_sec=1.0)
    t = 1000.0
    assert [rl.check("ip-a", now=t)[0] for _ in range(3)] == [True, True, True]  # burst
    allowed, retry = rl.check("ip-a", now=t)
    assert allowed is False and retry > 0                      # 4th is throttled
    # one second later exactly one token has refilled
    assert rl.check("ip-a", now=t + 1.0)[0] is True
    assert rl.check("ip-a", now=t + 1.0)[0] is False
    assert rl.stats()["rejected_total"] == 2


def test_rate_limit_is_per_client():
    rl = RateLimiter(capacity=1, refill_per_sec=0.1)
    t = 500.0
    assert rl.check("ip-a", now=t)[0] is True
    assert rl.check("ip-a", now=t)[0] is False   # a exhausted
    assert rl.check("ip-b", now=t)[0] is True    # b unaffected


def test_rate_limit_disabled_admits_everything():
    rl = RateLimiter(capacity=1, refill_per_sec=1.0, enabled=False)
    assert all(rl.check("ip-a", now=0)[0] for _ in range(20))


def test_rate_limit_429_over_the_wire(client, monkeypatch):
    """A client over its burst gets 429 + Retry-After; probes stay exempt."""
    from app.core import ratelimit
    tight = RateLimiter(capacity=2, refill_per_sec=0.01)
    monkeypatch.setattr(ratelimit, "rate_limiter", tight)
    import app.main as main_mod
    monkeypatch.setattr(main_mod, "rate_limiter", tight)

    codes = [client.get("/api/overview").status_code for _ in range(5)]
    assert 429 in codes
    limited = client.get("/api/overview")
    if limited.status_code == 429:
        assert limited.json()["code"] == "rate_limited"
        assert int(limited.headers["Retry-After"]) >= 1
    assert client.get("/api/health").status_code == 200   # exempt


# --- database circuit breaker --------------------------------------------------
def test_breaker_opens_after_threshold_then_half_opens_and_closes():
    cb = CircuitBreaker(failure_threshold=3, reset_timeout_s=5.0)
    t = 0.0
    assert cb.allow(now=t) is True and cb.state == CLOSED
    for _ in range(3):
        cb.record_failure(now=t)
    assert cb.state == OPEN
    assert cb.allow(now=t + 1.0) is False           # fails fast within the window
    assert cb.allow(now=t + 5.0) is True            # window elapsed → probe admitted
    assert cb.state == HALF_OPEN
    cb.record_success()                             # probe succeeds → closed
    assert cb.state == CLOSED
    assert cb.stats()["trips_total"] == 1


def test_breaker_reopens_on_failed_probe():
    cb = CircuitBreaker(failure_threshold=2, reset_timeout_s=3.0)
    cb.record_failure(now=0.0)
    cb.record_failure(now=0.0)
    assert cb.state == OPEN
    assert cb.allow(now=3.0) is True                # half-open probe
    cb.record_failure(now=3.0)                      # probe fails
    assert cb.state == OPEN
    assert cb.allow(now=3.5) is False               # re-armed window


def test_open_breaker_fast_fails_db_route(client):
    """With the breaker forced OPEN, a DB-backed route returns 503 immediately."""
    original = db_breaker._state, db_breaker._opened_at
    try:
        import time as _t
        db_breaker._state = OPEN
        db_breaker._opened_at = _t.monotonic()      # keep it open (no reset yet)
        res = client.get("/api/overview")
        assert res.status_code == 503
        assert res.json()["detail"]["code"] == "db_unavailable"
        assert client.get("/api/health").status_code == 200   # no DB → still ok
    finally:
        db_breaker._state, db_breaker._opened_at = original
        db_breaker.record_success()                 # ensure a clean state for other tests
