"""Live metrics endpoint — request volume, error rate, and latency percentiles
per endpoint, from the in-process registry. A real ops surface (and the source
for the front-end System Health panel)."""
from fastapi import APIRouter

from app.core.metrics import metrics

router = APIRouter(tags=["observability"])


@router.get("/metrics")
def get_metrics() -> dict:
    return metrics.snapshot()
