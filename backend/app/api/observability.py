"""Live metrics endpoint — request volume, error rate, and latency percentiles
per endpoint, from the in-process registry. A real ops surface (and the source
for the front-end System Health panel)."""
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.circuit import db_breaker
from app.core.concurrency import limiter
from app.core.database import pool_status
from app.core.metrics import metrics
from app.core.ratelimit import rate_limiter

router = APIRouter(tags=["observability"])


@router.get("/metrics")
def get_metrics() -> dict:
    """Request metrics plus the live reliability surface: the in-flight
    concurrency limiter (with how many requests it has shed), the per-client
    rate limiter, the database connection pool, and the DB circuit breaker."""
    return {
        **metrics.snapshot(),
        "concurrency": limiter.stats(),
        "rate_limit": rate_limiter.stats(),
        "database": pool_status(),
        "db_circuit": db_breaker.stats(),
    }


@router.get("/metrics/prometheus")
def get_metrics_prometheus() -> PlainTextResponse:
    """Prometheus text exposition — scrapeable by a real Prometheus/Grafana stack."""
    return PlainTextResponse(
        metrics.prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
