"""Span Risk Intelligence — deterministic, explainable, ranked, human-reviewed."""
from __future__ import annotations


def test_risk_board_is_ranked_and_bounded(client):
    board = client.get("/api/risk/spans").json()
    spans = board["spans"]
    assert len(spans) == 6                         # one per seeded plan
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
