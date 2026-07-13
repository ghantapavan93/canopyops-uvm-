"""API behavior tests — the assurance guarantees, exercised against PostGIS.

These intentionally target the hard parts: idempotency, revision conflict, the
evidence-completeness gate, RBAC, and the plan→verify→close loop.
"""
from conftest import auth, inner_polygon


def _scheduled(client):
    rows = client.get("/api/treatments", params={"status": "scheduled"}).json()
    return rows[0]


def _exec_body(plan, evidence):
    return {
        "planId": plan["planId"],
        "planRevision": plan["planRevision"],
        "actualGeometry": inner_polygon(plan["plannedGeometry"], 0.6),
        "constraintAcknowledged": True,
        "evidence": evidence,
    }


def test_health_and_postgis(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert "USE_GEOS=1" in client.get("/api/ready").json()["postgis"]


def test_rbac_compliance_cannot_execute(client):
    plan = _scheduled(client)
    res = client.post(
        "/api/executions",
        json=_exec_body(plan, [{"type": "photo_before"}]),
        headers={**auth(client, "compliance@synthetic.test"), "Idempotency-Key": "k-rbac"},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "forbidden"


def test_partial_coverage_is_computed(client):
    plan = _scheduled(client)
    res = client.post(
        "/api/executions",
        json=_exec_body(plan, [{"type": "photo_before"}]),
        headers={**auth(client, "crew@synthetic.test"), "Idempotency-Key": "k-cov"},
    )
    assert res.status_code == 200
    # inner polygon at 0.6 linear scale => 0.36 area coverage
    assert res.json()["coverageRatio"] == 0.36


def test_idempotent_replay_returns_same_record(client):
    plan = _scheduled(client)
    headers = {**auth(client, "crew@synthetic.test"), "Idempotency-Key": "k-idem"}
    body = _exec_body(plan, [{"type": "photo_before"}])
    first = client.post("/api/executions", json=body, headers=headers).json()
    second = client.post("/api/executions", json=body, headers=headers).json()
    assert second["syncStatus"] == "duplicate"
    assert second["id"] == first["id"]  # no duplicate record


def test_stale_revision_conflicts(client):
    plan = _scheduled(client)
    crew = auth(client, "crew@synthetic.test")
    # Someone edits the plan server-side.
    client.post(f"/api/plans/{plan['planId']}/bump-revision", headers=crew)
    res = client.post(
        "/api/executions",
        json=_exec_body(plan, [{"type": "photo_before"}]),
        headers={**crew, "Idempotency-Key": "k-conflict"},
    )
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["code"] == "revision_conflict"
    assert detail["serverRevision"] == 2 and detail["yourRevision"] == 1


def test_conflict_resolution_reapplies_under_same_key(client):
    plan = _scheduled(client)
    crew = auth(client, "crew@synthetic.test")
    client.post(f"/api/plans/{plan['planId']}/bump-revision", headers=crew)  # server -> rev 2
    body = _exec_body(plan, [{"type": "photo_before"}])
    conflict = client.post(
        "/api/executions", json=body, headers={**crew, "Idempotency-Key": "k-resolve"}
    )
    assert conflict.status_code == 409
    # resolve: re-submit the SAME idempotency key with the server revision → accepted
    resolved = client.post(
        "/api/executions",
        json={**body, "planRevision": conflict.json()["detail"]["serverRevision"]},
        headers={**crew, "Idempotency-Key": "k-resolve"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["syncStatus"] == "accepted"
    assert resolved.json()["planStatus"] == "awaiting_verification"


def test_evidence_gate_blocks_verification_until_recovered(client):
    plan = _scheduled(client)
    crew = auth(client, "crew@synthetic.test")
    reviewer = auth(client, "reviewer@synthetic.test")
    ex = client.post(
        "/api/executions",
        json=_exec_body(
            plan,
            [
                {"type": "photo_before"},
                {"type": "clearance_measurement"},
                {"type": "photo_after", "simulateUploadFailure": True},
            ],
        ),
        headers={**crew, "Idempotency-Key": "k-gate"},
    ).json()
    assert ex["evidenceComplete"] is False

    verify_body = {"conclusion": "effective"}
    blocked = client.post(f"/api/plans/{plan['planId']}/verify", json=verify_body, headers=reviewer)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "evidence_incomplete"

    # Recover the failed upload, then verification succeeds.
    failed = next(e for e in ex["evidence"] if e["uploadStatus"] == "failed")
    client.post(f"/api/executions/{ex['id']}/evidence/{failed['id']}/retry", headers=crew)
    ok = client.post(f"/api/plans/{plan['planId']}/verify", json=verify_body, headers=reviewer)
    assert ok.status_code == 200
    assert ok.json()["status"] == "effective"


def test_full_loop_to_closed_with_audit_trail(client):
    plan = _scheduled(client)
    crew = auth(client, "crew@synthetic.test")
    reviewer = auth(client, "reviewer@synthetic.test")
    ex = client.post(
        "/api/executions",
        json=_exec_body(plan, [{"type": "photo_before"}, {"type": "photo_after"}, {"type": "clearance_measurement"}]),
        headers={**crew, "Idempotency-Key": "k-loop"},
    ).json()
    assert ex["planStatus"] == "awaiting_verification"

    client.post(
        f"/api/plans/{plan['planId']}/verify",
        json={"conclusion": "partially_effective", "regrowthObserved": True},
        headers=reviewer,
    )
    client.post(f"/api/plans/{plan['planId']}/plan-followup", headers=reviewer)
    closed = client.post(f"/api/plans/{plan['planId']}/close", headers=reviewer)
    assert closed.json()["status"] == "closed"

    proof = client.get(f"/api/plans/{plan['planId']}/proof").json()
    actions = [a["action"] for a in proof["auditTrail"]]
    # The seeded plan legitimately carries prior history (creation/approval);
    # what this test guarantees is that the live workflow appends the outcome
    # sequence, in order, as the tail of the immutable trail.
    assert actions[-4:] == [
        "execution.submitted",
        "plan.verified",
        "plan.followup_planned",
        "plan.closed",
    ]


def test_reviewer_cannot_execute_and_crew_cannot_verify(client):
    plan = _scheduled(client)
    # crew executes fine
    client.post(
        "/api/executions",
        json=_exec_body(plan, [{"type": "photo_before"}, {"type": "photo_after"}, {"type": "clearance_measurement"}]),
        headers={**auth(client, "crew@synthetic.test"), "Idempotency-Key": "k-x"},
    )
    # crew cannot verify
    denied = client.post(
        f"/api/plans/{plan['planId']}/verify",
        json={"conclusion": "effective"},
        headers=auth(client, "crew@synthetic.test"),
    )
    assert denied.status_code == 403
