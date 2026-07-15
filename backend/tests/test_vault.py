"""Compliance evidence vault — the auto-assembled dossier mapped to NERC/TVMP/
NESC/environmental/QA requirements, driven by the live record chain."""
from __future__ import annotations

from tests.conftest import auth

_FRAMEWORKS = {"NERC FAC-003", "TVMP", "NESC", "Environmental / SWPPP", "QA (checks & balances)"}


def test_vault_index_shape(client):
    b = client.get("/api/vault").json()
    assert b["plans"], "expected per-plan dossiers"
    assert b["summary"]["plans"] == len(b["plans"])
    d = b["plans"][0]
    assert {f["code"] for f in d["frameworks"]} == _FRAMEWORKS


def test_completeness_matches_satisfied_ratio(client):
    for d in client.get("/api/vault").json()["plans"]:
        satisfied = sum(1 for f in d["frameworks"] if f["satisfied"])
        assert d["satisfied"] == satisfied
        assert d["completenessPct"] == round(satisfied / d["requirements"] * 100)


def test_prescription_requirement_always_satisfied(client):
    # every plan carries a prescription (method + target condition)
    for d in client.get("/api/vault").json()["plans"]:
        tvmp = next(f for f in d["frameworks"] if f["code"] == "TVMP")
        assert tvmp["satisfied"] is True
        assert d["prescription"]["method"]


def test_qa_requirement_flips_after_a_passing_audit(client):
    # pick a plan and confirm QA is initially unsatisfied
    plan_id = client.get("/api/vault").json()["plans"][0]["planId"]
    before = client.get(f"/api/vault/plans/{plan_id}").json()
    qa_before = next(f for f in before["frameworks"] if f["code"].startswith("QA"))
    assert qa_before["satisfied"] is False

    client.post(f"/api/audit/plans/{plan_id}", json={"outcome": "pass"},
                headers=auth(client, "reviewer@synthetic.test"))

    after = client.get(f"/api/vault/plans/{plan_id}").json()
    qa_after = next(f for f in after["frameworks"] if f["code"].startswith("QA"))
    assert qa_after["satisfied"] is True
    assert after["completenessPct"] >= before["completenessPct"]
    assert after["components"]["qaOutcome"] == "pass"


def test_dossier_404_for_unknown_plan(client):
    assert client.get("/api/vault/plans/nope-0000").status_code == 404


def test_evidence_chain_reports_integrity(client):
    # a dossier lists evidence items with their stored status + integrity fields
    seen_item = False
    for d in client.get("/api/vault").json()["plans"]:
        for item in d["components"]["evidence"]:
            seen_item = True
            assert "stored" in item and "uploadStatus" in item and "checksum" in item
    assert seen_item, "expected at least one evidence item across the vault"
