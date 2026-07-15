"""Reliability-outcome model — the quantitative 'closed ≠ effective' view.
Movement is synthetic but must be internally consistent and driven by real
record state (so the endpoint can't just print flattering numbers)."""
from __future__ import annotations


def test_reliability_board_shape_and_disclaimer(client):
    body = client.get("/api/reliability").json()
    assert "synthetic" in body["note"].lower()
    assert body["circuits"], "expected per-circuit rows from the seed"
    assert body["rollup"]["circuits"] == len(body["circuits"])


def test_caidi_is_saidi_over_saifi(client):
    for c in client.get("/api/reliability").json()["circuits"]:
        # CAIDI = SAIDI / SAIFI, within rounding
        assert abs(c["caidiBefore"] - c["saidiBefore"] / c["saifiBefore"]) < 0.2
        assert abs(c["caidiAfter"] - c["saidiAfter"] / c["saifiAfter"]) < 0.2


def test_effective_circuits_improve_ineffective_barely_move(client):
    for c in client.get("/api/reliability").json()["circuits"]:
        # improvement (negative delta) only when effectiveness is real
        if c["classification"] == "effective":
            assert c["saidiDelta"] <= -3.0
            assert c["saidiAfter"] < c["saidiBefore"]
        if c["classification"] == "closed_not_effective":
            assert c["closed"] > 0
            assert c["saidiDelta"] > -1.0        # closed, but reliability didn't move


def test_closed_split_adds_up(client):
    for c in client.get("/api/reliability").json()["circuits"]:
        assert c["effectiveClosures"] + c["ineffectiveClosures"] == c["closed"]
        assert 0 <= c["effectivenessPct"] <= 100


def test_cmi_equals_saidi_times_customers(client):
    for c in client.get("/api/reliability").json()["circuits"]:
        assert c["cmiBefore"] == round(c["saidiBefore"] * c["customersServed"])
        assert c["cmiAfter"] == round(c["saidiAfter"] * c["customersServed"])


def test_rollup_totals_match_circuits(client):
    body = client.get("/api/reliability").json()
    circuits, rollup = body["circuits"], body["rollup"]
    assert rollup["closedTotal"] == sum(c["closed"] for c in circuits)
    assert rollup["effectiveTotal"] == sum(c["effectiveClosures"] for c in circuits)
    assert rollup["customers"] == sum(c["customersServed"] for c in circuits)


def test_reliability_is_deterministic(client):
    a = client.get("/api/reliability").json()["circuits"]
    b = client.get("/api/reliability").json()["circuits"]
    assert [c["saidiAfter"] for c in a] == [c["saidiAfter"] for c in b]
