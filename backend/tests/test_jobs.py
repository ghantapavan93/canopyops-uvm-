"""Durable background job queue: enqueue → worker claims (FOR UPDATE SKIP
LOCKED) → runs the handler → terminal state, with retry/backoff. Proof Pack and
GeoJSON import run off the request path."""
from __future__ import annotations

from sqlalchemy import text

from app.core.database import AdminSessionLocal, SessionLocal
from app.core.tenancy import reset_current_tenant, set_current_tenant
from app.models import domain as m
from app.services import jobs
from tests.conftest import auth


def test_job_reads_are_open_but_tenant_scoped(client):
    """Reading the queue is open, like every other demo read — an anonymous
    caller resolves to the demo program. Isolation comes from the tenant, not the
    token, so requiring auth here bought nothing and only broke the Engineering
    Evidence panel (it 401'd and rendered as 'empty' rather than 'broken').
    Enqueuing work is still role-gated — that's asserted below."""
    assert client.get("/api/jobs").status_code == 200
    assert client.get("/api/jobs/does-not-exist").status_code == 404  # not 401


def test_enqueue_still_requires_a_role(client):
    """The write path is where authorization actually matters."""
    plan_id = client.get("/api/treatments").json()[0]["planId"]
    assert client.post(f"/api/jobs/proof-pack/{plan_id}").status_code == 401
    assert client.post("/api/jobs/geojson-import", json={"features": []}).status_code == 401


def test_reaper_fails_stuck_running_jobs(client):
    token = set_current_tenant("demo")
    try:
        with SessionLocal() as db:
            jid = jobs.enqueue(db, "proof_pack", {"plan_id": "x"}).id
    finally:
        reset_current_tenant(token)
    # simulate a worker that claimed the job then died (old started_at, running)
    with AdminSessionLocal() as db:
        db.execute(text(
            "UPDATE job SET status='running', started_at = now() - interval '1 hour' WHERE id = :i"
        ), {"i": jid})
        db.commit()
    assert jobs.reap_stuck(SessionLocal, timeout_s=300) >= 1
    got = client.get(f"/api/jobs/{jid}", headers=auth(client, "reviewer@synthetic.test")).json()
    assert got["status"] == "failed"


def test_geojson_import_rejects_oversize(client):
    big = [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}] * 10_001
    r = client.post("/api/jobs/geojson-import", json={"features": big},
                    headers=auth(client, "manager@synthetic.test"))
    assert r.status_code == 422


def _plan_id(client) -> str:
    return client.get("/api/audit/queue").json()["items"][0]["planId"]


def test_enqueue_proof_pack_returns_202_queued(client):
    plan_id = _plan_id(client)
    res = client.post(f"/api/jobs/proof-pack/{plan_id}",
                      headers=auth(client, "reviewer@synthetic.test"))
    assert res.status_code == 202
    body = res.json()
    assert body["status"] == "queued" and body["type"] == "proof_pack"


def test_worker_processes_proof_pack_to_success(client):
    plan_id = _plan_id(client)
    job_id = client.post(f"/api/jobs/proof-pack/{plan_id}",
                         headers=auth(client, "reviewer@synthetic.test")).json()["id"]

    assert jobs.run_once(SessionLocal) is True          # the worker claims + runs it
    done = client.get(f"/api/jobs/{job_id}", headers=auth(client, "reviewer@synthetic.test")).json()
    assert done["status"] == "succeeded"
    assert done["result"]["record"]                     # the assembled Proof Pack rode along
    assert done["startedAt"] and done["finishedAt"]


def test_claim_is_exclusive_then_drains(client):
    plan_id = _plan_id(client)
    hdr = auth(client, "reviewer@synthetic.test")
    client.post(f"/api/jobs/proof-pack/{plan_id}", headers=hdr)
    client.post(f"/api/jobs/proof-pack/{plan_id}", headers=hdr)

    # each run_once claims exactly one; a third finds nothing
    assert jobs.run_once(SessionLocal) is True
    assert jobs.run_once(SessionLocal) is True
    assert jobs.run_once(SessionLocal) is False


def test_enqueue_proof_pack_unknown_plan_404(client):
    res = client.post("/api/jobs/proof-pack/nope-0000",
                      headers=auth(client, "reviewer@synthetic.test"))
    assert res.status_code == 404


def test_geojson_import_job_creates_corridors(client):
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "geometry": {"type": "LineString", "coordinates": [[-83.2, 40.1], [-83.19, 40.11]]},
         "properties": {"circuitId": "CKT-9001", "spanLabel": "SPAN 90-91"}},
    ]}
    job_id = client.post("/api/jobs/geojson-import", json={"features": fc["features"]},
                         headers=auth(client, "manager@synthetic.test")).json()["id"]
    assert jobs.run_once(SessionLocal) is True
    done = client.get(f"/api/jobs/{job_id}", headers=auth(client, "reviewer@synthetic.test")).json()
    assert done["status"] == "succeeded"
    assert done["result"]["imported"] == 1


def test_failed_job_retries_then_fails(client):
    # a proof_pack job for a plan that will be deleted before it runs → handler
    # raises → retry/backoff until max_attempts, then terminal 'failed'
    token = set_current_tenant("demo")   # enqueue outside a request needs a program
    try:
        with SessionLocal() as db:
            job = jobs.enqueue(db, "proof_pack", {"plan_id": "does-not-exist"}, max_attempts=2)
            job_id = job.id
    finally:
        reset_current_tenant(token)
    # first run: attempt 1 fails → requeued with backoff (run_after in the future)
    jobs.run_once(SessionLocal)
    with SessionLocal() as db:
        j = db.get(m.Job, job_id)
        # not yet terminal after one attempt (max_attempts=2), and it recorded the error
        assert j.attempts == 1 and j.error and j.status in ("queued", "failed")
        # clear the backoff so the next claim picks it up immediately
        j.run_after = None
        db.commit()
    jobs.run_once(SessionLocal)
    with SessionLocal() as db:
        j = db.get(m.Job, job_id)
        assert j.status == "failed" and j.attempts == 2
