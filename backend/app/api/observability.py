"""Live metrics endpoint — request volume, error rate, and latency percentiles
per endpoint, from the in-process registry. A real ops surface (and the source
for the front-end System Health panel)."""
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.metrics import metrics

router = APIRouter(tags=["observability"])


@router.get("/metrics")
def get_metrics() -> dict:
    return metrics.snapshot()


@router.get("/metrics/prometheus")
def get_metrics_prometheus() -> PlainTextResponse:
    """Prometheus text exposition — scrapeable by a real Prometheus/Grafana stack."""
    return PlainTextResponse(
        metrics.prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
