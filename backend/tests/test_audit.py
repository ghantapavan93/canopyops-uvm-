"""Work-plan QA audit — the independent checks-and-balances pass. Objective
checks are computed server-side; a certified reviewer records the verdict
(append-only, RBAC-gated)."""
from __future__ import annotations

from tests.conftest import auth


def test_audit_queue_shape_and_checks(client):
    b = client.get("/api/audit/queue").json()
    assert b["items"], "expected auditable (executed) plans"
    item = b["items"][0]
    keys = {c["key"] for c in item["checks"]}
    assert keys == {"coverage", "evidence", "integrity", "verification", "constraints"}
    assert b["summary"]["total"] == len(b["items"])


def test_audit_score_matches_passed_ratio(client):
    for item in client.get("/api/audit/queue").json()["items"]:
        passed = sum(1 for c in item["checks"] if c["passed"])
        assert abs(item["score"] - passed / len(item["checks"])) < 1e-6


def test_suggested_outcome_caps_at_fail_on_critical_miss(client):
    for item in client.get("/api/audit/queue").json()["items"]:
        critical_fail = any(c["critical"] and not c["passed"] for c in item["checks"])
        if critical_fail:
            assert item["suggestedOutcome"] == "fail"
        elif item["score"] >= 0.999:
            assert item["suggestedOutcome"] == "pass"
        else:
            assert item["suggestedOutcome"] == "conditional"


def test_record_audit_requires_reviewer_role(client):
    plan_id = client.get("/api/audit/queue").json()["items"][0]["planId"]
    # a field crew may not audit
    denied = client.post(f"/api/audit/plans/{plan_id}", json={"outcome": "pass"},
                         headers=auth(client, "crew@synthetic.test"))
    assert denied.status_code == 403
    # unauthenticated
    assert client.post(f"/api/audit/plans/{plan_id}", json={"outcome": "pass"}).status_code == 401


def test_record_audit_persists_snapshot_and_history(client):
    plan_id = client.get("/api/audit/queue").json()["items"][0]["planId"]
    hdr = auth(client, "reviewer@synthetic.test")
    res = client.post(f"/api/audit/plans/{plan_id}",
                      json={"outcome": "conditional", "note": "recover the failed upload"}, headers=hdr)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["outcome"] == "conditional"
    assert body["auditorName"]
    assert len(body["checks"]) == 5              # the objective checks are snapshotted

    hist = client.get(f"/api/audit/plans/{plan_id}").json()
    assert len(hist) == 1 and hist[0]["outcome"] == "conditional"

    # the queue now reflects the audit
    item = next(i for i in client.get("/api/audit/queue").json()["items"] if i["planId"] == plan_id)
    assert item["audited"] is True and item["lastOutcome"] == "conditional"


def test_invalid_outcome_rejected(client):
    plan_id = client.get("/api/audit/queue").json()["items"][0]["planId"]
    res = client.post(f"/api/audit/plans/{plan_id}", json={"outcome": "great"},
                      headers=auth(client, "compliance@synthetic.test"))
    assert res.status_code == 422


def test_audit_writes_immutable_audit_event(client):
    plan_id = client.get("/api/audit/queue").json()["items"][0]["planId"]
    client.post(f"/api/audit/plans/{plan_id}", json={"outcome": "pass"},
                headers=auth(client, "reviewer@synthetic.test"))
    # the business audit trail carries the event (surfaced via the overview feed)
    actions = [a["action"] for a in client.get("/api/overview").json()["recentActivity"]]
    assert "workplan.audited" in actions
