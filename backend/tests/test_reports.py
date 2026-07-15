"""Compliance report — the exportable program-evidence rollup."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def test_report_scopes_to_a_single_circuit(client):
    full = client.get("/api/reports/compliance").json()
    circuit = full["spans"][0]["circuit"]
    scoped = client.get(f"/api/reports/compliance?circuit={circuit}").json()
    assert scoped["totalPlans"] < full["totalPlans"]
    assert all(s["circuit"] == circuit for s in scoped["spans"])


def test_report_scopes_by_activity_date(client):
    full = client.get("/api/reports/compliance").json()
    since = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    scoped = client.get("/api/reports/compliance", params={"since": since}).json()
    # Executed spans are dated ~15-19 days back in the seed, so a 10-day window
    # excludes them and keeps the recently-touched (unexecuted) plans.
    assert 1 <= scoped["totalPlans"] < full["totalPlans"]


def test_report_pdf_is_a_real_pdf(client):
    res = client.get("/api/reports/compliance.pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert "attachment" in res.headers["content-disposition"]
    assert res.content[:5] == b"%PDF-"          # a real PDF file signature
    assert len(res.content) > 1000

    scoped = client.get("/api/reports/compliance.pdf?circuit=CKT-8842")
    assert scoped.status_code == 200
    assert "CKT-8842" in scoped.headers["content-disposition"]
