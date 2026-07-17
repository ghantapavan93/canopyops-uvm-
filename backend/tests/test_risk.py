"""Span Risk Intelligence — deterministic, explainable, ranked, human-reviewed."""
from __future__ import annotations

from tests.conftest import auth


def test_risk_board_is_ranked_and_bounded(client):
    board = client.get("/api/risk/spans").json()
    spans = board["spans"]
    # One per seeded plan — derived, not a literal, so growing the demo data
    # doesn't break the invariant this test is actually about.
    seeded = len(client.get("/api/treatments", params={"limit": 500}).json())
    assert len(spans) == seeded
    scores = [s["score"] for s in spans]
    assert scores == sorted(scores, reverse=True)  # highest risk first
    for s in spans:
        assert 0 <= s["score"] <= 100
        assert s["level"] in ("low", "elevated", "high", "critical")
        assert s["requiresReview"] is True         # never machine-authorized
        assert "pending forester review" in s["recommendation"]


def test_factors_are_transparent_and_sum_to_score(client):
    spans = client.get("/api/risk/spans").json()["spans"]
    s = spans[0]
    # weights are the documented model and cover 100 points
    assert sum(f["weight"] for f in s["factors"]) == 100
    # the composite is exactly the sum of factor contributions (no hidden terms)
    assert round(sum(f["contribution"] for f in s["factors"]), 1) == s["score"]
    # every factor explains itself
    assert all(f["note"] for f in s["factors"])


def test_scoring_is_deterministic(client):
    a = client.get("/api/risk/spans").json()["spans"]
    b = client.get("/api/risk/spans").json()["spans"]
    assert [x["score"] for x in a] == [x["score"] for x in b]


def test_hftd_intersection_lifts_wildfire_factor(client):
    spans = client.get("/api/risk/spans").json()["spans"]
    fire = {s["workOrderRef"]: next(f for f in s["factors"] if f["name"] == "wildfire")
            for s in spans}
    # At least one seeded span intersects the HFTD zone and gets the high signal.
    assert any(f["value"] >= 0.9 for f in fire.values())


def test_review_persists_and_marks_the_span_reviewed(client):
    spans = client.get("/api/risk/spans").json()["spans"]
    target = spans[0]
    assert target["reviewed"] is False

    res = client.post(
        f"/api/risk/spans/{target['planId']}/review",
        json={"decision": "acknowledged", "note": "Validated the ranking on site."},
        headers=auth(client, "reviewer@synthetic.test"),
    )
    assert res.status_code == 200, res.text
    review = res.json()
    assert review["reviewerName"]
    assert review["score"] == target["score"]      # snapshotted the score the reviewer saw

    # The board now reflects the durable review (survives a fresh read).
    again = next(s for s in client.get("/api/risk/spans").json()["spans"]
                 if s["planId"] == target["planId"])
    assert again["reviewed"] is True
    assert again["reviewedBy"]
    assert again["reviewedAt"]


def test_review_requires_a_reviewer_role(client):
    plan_id = client.get("/api/risk/spans").json()["spans"][0]["planId"]
    res = client.post(
        f"/api/risk/spans/{plan_id}/review",
        json={"decision": "acknowledged"},
        headers=auth(client, "crew@synthetic.test"),   # field crew may not sign off
    )
    assert res.status_code == 403


def test_review_writes_an_immutable_audit_event(client):
    plan_id = client.get("/api/risk/spans").json()["spans"][0]["planId"]
    client.post(
        f"/api/risk/spans/{plan_id}/review",
        json={"decision": "acknowledged"},
        headers=auth(client, "compliance@synthetic.test"),
    )
    proof = client.get(f"/api/plans/{plan_id}/proof").json()
    assert any(a["action"] == "risk.reviewed" for a in proof["auditTrail"])


def test_revoke_reopens_the_span_and_history_is_append_only(client):
    hdr = auth(client, "reviewer@synthetic.test")
    plan_id = client.get("/api/risk/spans").json()["spans"][0]["planId"]

    client.post(f"/api/risk/spans/{plan_id}/review", json={"decision": "acknowledged"}, headers=hdr)
    reviewed = next(s for s in client.get("/api/risk/spans").json()["spans"] if s["planId"] == plan_id)
    assert reviewed["reviewed"] is True

    # Revoke reopens the span — but nothing is deleted.
    client.post(f"/api/risk/spans/{plan_id}/review", json={"decision": "revoked", "note": "clearance changed"}, headers=hdr)
    reopened = next(s for s in client.get("/api/risk/spans").json()["spans"] if s["planId"] == plan_id)
    assert reopened["reviewed"] is False
    assert reopened["reviewedBy"] is None

    history = client.get(f"/api/risk/spans/{plan_id}/reviews").json()
    assert len(history) == 2                                   # both events preserved
    assert history[0]["decision"] == "revoked"                 # newest first
    assert history[1]["decision"] == "acknowledged"


def test_review_history_empty_for_unreviewed_span(client):
    plan_id = client.get("/api/risk/spans").json()["spans"][-1]["planId"]
    assert client.get(f"/api/risk/spans/{plan_id}/reviews").json() == []
