"""The free-tier fallback: the queue must actually drain inside the API process."""
import threading, time
from app import worker


def test_in_process_worker_drains_a_job(monkeypatch):
    drained = threading.Event()

    def fake_run_once():
        drained.set()
        return False

    monkeypatch.setattr(worker.jobs, "run_once", fake_run_once)
    monkeypatch.setattr(worker.jobs, "reap_stuck", lambda: 0)

    stop = threading.Event()
    t = worker.start_in_process(stop)
    try:
        assert drained.wait(timeout=5), "in-process worker never ran the drain loop"
        assert t.daemon, "must be a daemon thread or it blocks API shutdown"
    finally:
        stop.set()
        t.join(timeout=10)
    assert not t.is_alive(), "worker thread must stop when the API shuts down"
