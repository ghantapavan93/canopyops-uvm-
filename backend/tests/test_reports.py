"""Compliance report — the exportable program-evidence rollup."""
from __future__ import annotations

from tests.conftest import auth


def test_compliance_report_shape_and_totals(client):
    r = client.get("/api/reports/compliance").json()
    assert r["totalPlans"] == 6
    assert len(r["spans"]) == 6
    assert 0 <= r["attainmentPct"] <= 100
    assert 0 <= r["evidenceCompletePct"] <= 100
    # risk distribution covers every span
    assert sum(r["riskDistribution"].values()) == 6
    # spans are ranked by risk, highest first
    scores = [s["riskScore"] for s in r["spans"]]
    assert scores == sorted(scores, reverse=True)


def test_report_reflects_a_persisted_review(client):
    before = client.get("/api/reports/compliance").json()
    assert before["reviewedPct"] == 0.0

    plan_id = client.get("/api/risk/spans").json()["spans"][0]["planId"]
    client.post(f"/api/risk/spans/{plan_id}/review", json={"decision": "acknowledged"},
                headers=auth(client, "reviewer@synthetic.test"))

    after = client.get("/api/reports/compliance").json()
    assert after["reviewedPct"] > 0.0
    assert any(s["reviewed"] for s in after["spans"])


def test_report_flags_hftd_exposure(client):
    r = client.get("/api/reports/compliance").json()
    assert r["hftdIntersecting"] >= 1     # a seeded span intersects the HFTD zone
