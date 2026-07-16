"""Background worker process — drains the durable job queue off the request path.

Runs as its own container (`python -m app.worker`) against the same database and
image as the API, so Proof Pack generation and large GeoJSON imports never block
a user request and can be scaled independently. Polls for runnable jobs; sleeps
briefly when the queue is empty. Traces are exported via the same OTel wiring.
"""
from __future__ import annotations

import logging
import signal
import time

from app.core.database import engine
from app.core.logging import setup_logging
from app.core.telemetry import setup_tracing_core
from app.services import jobs

setup_logging()
logger = logging.getLogger("canopyops")

_POLL_INTERVAL_S = 1.0
_running = True


def _stop(*_a) -> None:
    global _running
    _running = False


def main() -> None:
    setup_tracing_core(engine, "-worker")   # DB spans + provider, no FastAPI
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info("worker_started")
    idle = 0
    ticks = 0
    while _running:
        try:
            # Periodically fail jobs a dead worker left stuck in 'running'.
            ticks += 1
            if ticks % 30 == 0:
                jobs.reap_stuck()
            did_work = jobs.run_once()
        except Exception:  # noqa: BLE001 — never let the loop die
            logger.exception("worker_loop_error")
            did_work = False
        if did_work:
            idle = 0
        else:
            idle = min(idle + 1, 5)
            time.sleep(_POLL_INTERVAL_S * idle)
    logger.info("worker_stopped")


if __name__ == "__main__":
    main()
