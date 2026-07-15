"""Scalability & reliability guarantees:
  * a runaway query is cancelled by Postgres' statement_timeout (not left to pin
    a pooled connection forever),
  * the in-flight limiter sheds load past its cap while leaving probes answerable,
  * the metrics endpoint exposes the live concurrency + connection-pool surface.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.concurrency import InFlightLimiter, limiter
from app.core.database import build_engine


def test_statement_timeout_cancels_runaway_query():
    """A query exceeding statement_timeout is cancelled server-side."""
    engine = build_engine(statement_timeout_ms=250)
    try:
        with engine.connect() as conn:
            with pytest.raises(Exception) as excinfo:
                conn.execute(text("SELECT pg_sleep(2)"))  # 2s >> 250ms budget
        msg = str(excinfo.value).lower()
        assert "statement timeout" in msg or "canceling" in msg
    finally:
        engine.dispose()


def test_inflight_limiter_admits_then_sheds_then_recovers():
    lim = InFlightLimiter(max_concurrent=2)
    assert lim.try_acquire() is True          # 1
    assert lim.try_acquire() is True          # 2 (at cap)
    assert lim.try_acquire() is False         # shed
    assert lim.stats()["shed_total"] == 1
    assert lim.stats()["peak"] == 2
    lim.release()
    assert lim.try_acquire() is True          # slot freed → admitted again
    assert lim.stats()["in_flight"] == 2


def test_limiter_zero_disables_the_cap():
    lim = InFlightLimiter(max_concurrent=0)
    assert all(lim.try_acquire() for _ in range(50))
    assert lim.stats()["shed_total"] == 0


def test_load_shedding_returns_503_and_keeps_probes_answerable(client):
    """At capacity, a normal request is shed with 503 + Retry-After, but the
    liveness/readiness probes are exempt so orchestrators can still tell
    'overloaded' apart from 'down'."""
    orig_max, orig_n = limiter.max, limiter._n
    try:
        limiter.max = 1
        limiter._n = 1  # simulate one request already in flight → at capacity
        shed = client.get("/api/metrics")
        assert shed.status_code == 503
        assert shed.json()["code"] == "overloaded"
        assert shed.headers.get("Retry-After") == "1"
        assert client.get("/api/health").status_code == 200   # exempt
    finally:
        limiter.max, limiter._n = orig_max, orig_n


def test_metrics_exposes_concurrency_and_pool(client):
    client.get("/api/overview")  # generate some traffic
    body = client.get("/api/metrics").json()
    assert {"in_flight", "limit", "shed_total", "peak"} <= set(body["concurrency"])
    assert "statement_timeout_ms" in body["database"]
