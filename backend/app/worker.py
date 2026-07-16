"""Background worker — drains the durable job queue off the request path.

PREFERRED topology: its own container (`python -m app.worker`) against the same
database and image as the API, so Proof Pack generation and large GeoJSON
imports never block a user request and can be scaled independently.

FALLBACK topology (`RUN_WORKER_IN_PROCESS=true`): the same loop on a daemon
thread inside the API process. This exists only for hosts whose free tier has no
background-service type at all (e.g. Render free), where the alternative is that
queued jobs are never processed. It is a genuine downgrade — the worker dies with
the web process, cannot scale separately, and shares the API's CPU — so it is
opt-in and off by default. Claim the container topology only where it is the one
actually deployed.
"""
from __future__ import annotations

import logging
import signal
import threading
import time
from typing import Callable

from app.core.database import engine
from app.core.logging import setup_logging
from app.core.telemetry import setup_tracing_core
from app.services import jobs

logger = logging.getLogger("canopyops")

_POLL_INTERVAL_S = 1.0
_running = True


def _stop(*_a) -> None:
    global _running
    _running = False


def run_loop(is_running: Callable[[], bool]) -> None:
    """The drain loop itself. Takes its stop condition as a callable so it can be
    driven by a signal flag (own process) or an Event (in-process thread)."""
    idle = 0
    ticks = 0
    while is_running():
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


def start_in_process(stop: threading.Event) -> threading.Thread:
    """Run the drain loop on a daemon thread inside the API process.

    Does NOT touch telemetry — the API has already configured it; re-running the
    tracing setup here would double-instrument the engine. Claiming a job is safe
    across processes/threads because claim_next uses FOR UPDATE SKIP LOCKED, so
    even if several API workers each start a thread they cannot double-process a
    job (they will merely poll redundantly — prefer web_concurrency=1).
    """
    thread = threading.Thread(
        target=run_loop,
        args=(lambda: not stop.is_set(),),
        name="canopyops-worker",
        daemon=True,
    )
    thread.start()
    logger.warning(
        "worker_started_in_process — degraded topology: the job queue is draining "
        "inside the API process, not a dedicated worker container."
    )
    return thread


def main() -> None:
    setup_logging()
    setup_tracing_core(engine, "-worker")   # DB spans + provider, no FastAPI
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info("worker_started")
    run_loop(lambda: _running)
    logger.info("worker_stopped")


if __name__ == "__main__":
    main()
