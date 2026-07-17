"""The golden record — the demonstration's anchor.

WO-2026-0142 is the one record every module tells a chapter of. If it silently
drifts (evidence completes itself, coverage changes, the constraint stops
intersecting), the demo still "works" but stops telling the story it claims to.
These pin the parts a reviewer is actually shown.
"""
from conftest import auth

from app.seed import GOLDEN_REF


def _golden(client) -> dict:
    rows = client.get("/api/treatments", params={"limit": 500}).json()
    match = [r for r in rows if r["workOrderRef"] == GOLDEN_REF]
    assert match, f"{GOLDEN_REF} is missing — the demo has no anchor record"
    return match[0]


def test_golden_record_is_worked_but_not_verifiable(client):
    """The whole product thesis in one row: the work is recorded, and it is still
    NOT verified — because an evidence upload failed."""
    g = _golden(client)
    assert g["status"] == "awaiting_verification"
    assert g["evidenceComplete"] is False, "the failed photo must keep evidence incomplete"
    assert 0 < g["evidenceScore"] < 1


def test_golden_record_has_real_partial_coverage(client):
    """Coverage is computed from the planned/actual geometry by the same path the
    app uses — never written into the seed. The crew fell short on the south
    edge, so this must be a real gap a human has to judge, not a tidy 100%."""
    g = _golden(client)
    assert g["coverageRatio"] is not None
    assert 0.85 <= g["coverageRatio"] <= 0.88, g["coverageRatio"]


def test_golden_record_intersects_the_water_buffer(client):
    """The riparian buffer is why the plan was cut 7.4 -> 6.8 acres. It must be a
    real PostGIS intersection, not a label."""
    g = _golden(client)
    assert "water_buffer" in g["constraintFlags"], g["constraintFlags"]


def test_golden_record_carries_the_decision_trail(client):
    """A reviewer should be able to read WHY the plan moved, not just that it did."""
    g = _golden(client)
    res = client.get(f"/api/plans/{g['planId']}/proof")
    assert res.status_code == 200, res.text
    pack = res.json()
    actions = {a["action"] for a in pack["auditTrail"]}
    assert {"plan.constraint_detected", "plan.revised", "evidence.failed"} <= actions, actions
    assert g["planRevision"] == 3, "the buffer adjustment took the plan to revision 3"


def test_demo_reset_restores_the_golden_record(client):
    """Reset is the reviewer's undo — it must bring the anchor back."""
    res = client.post("/api/demo/reset")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["goldenRecord"] == GOLDEN_REF
    assert body["counts"]["plans"] > 0
    _golden(client)  # still there, still the anchor
