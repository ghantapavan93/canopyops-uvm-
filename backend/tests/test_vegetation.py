"""Vegetation intelligence — hot-spotting heat + cycle-buster watchlist.
Scores/geometry are driven by real record state; the model must be internally
consistent and deterministic."""
from __future__ import annotations


# --- hot-spotting -------------------------------------------------------------
def test_hotspots_shape_and_geometry(client):
    b = client.get("/api/vegetation/hotspots").json()
    assert "synthetic" in b["note"].lower() or "illustrative" in b["note"].lower()
    assert b["hotspots"], "expected per-span hot-spot cells"
    top = b["hotspots"][0]
    # ranked hottest-first
    assert top["hotspotScore"] >= b["hotspots"][-1]["hotspotScore"]
    # real corridor centerline geometry travels with each cell (for the heat layer)
    assert top["geometry"]["type"] in ("LineString", "MultiLineString")


def test_hotspot_score_bounds_and_tier(client):
    for c in client.get("/api/vegetation/hotspots").json()["hotspots"]:
        assert 0 <= c["hotspotScore"] <= 100
        expected = "hot" if c["hotspotScore"] >= 66 else "elevated" if c["hotspotScore"] >= 40 else "stable"
        assert c["tier"] == expected
        assert c["reactiveRepeats"] + c["plannedVisits"] >= 0


def test_hotspot_summary_counts_match(client):
    b = client.get("/api/vegetation/hotspots").json()
    cells, s = b["hotspots"], b["summary"]
    assert s["total"] == len(cells)
    assert s["hot"] == sum(1 for c in cells if c["tier"] == "hot")
    assert s["elevated"] == sum(1 for c in cells if c["tier"] == "elevated")
    assert s["stable"] == sum(1 for c in cells if c["tier"] == "stable")
    if cells:
        assert s["maxScore"] == cells[0]["hotspotScore"]


# --- cycle busters ------------------------------------------------------------
def test_cycle_busters_ranked_by_days_to_conflict(client):
    spans = client.get("/api/vegetation/cycle-busters").json()["spans"]
    assert spans
    days = [s["daysToConflict"] for s in spans]
    assert days == sorted(days), "watchlist must be soonest-conflict first"


def test_days_to_conflict_matches_headroom_over_growth(client):
    for s in client.get("/api/vegetation/cycle-busters").json()["spans"]:
        expected = int(s["mvcdHeadroomFt"] / (s["growthFtPerYear"] / 365.0))
        assert s["daysToConflict"] == expected
        # priority thresholds (relative to the trim cycle)
        d = s["daysToConflict"]
        want = "hazard" if d < 200 else "elevated" if d < 400 else "watch"
        assert s["priority"] == want


def test_cycle_buster_flag_tracks_growth_rate(client):
    for s in client.get("/api/vegetation/cycle-busters").json()["spans"]:
        assert s["isCycleBuster"] == (s["growthFtPerYear"] >= 3.0)


def test_cycle_buster_summary(client):
    b = client.get("/api/vegetation/cycle-busters").json()
    spans, s = b["spans"], b["summary"]
    assert s["watchlistTotal"] == len(spans)
    assert s["cycleBusters"] == sum(1 for x in spans if x["isCycleBuster"])
    assert s["imminent"] == sum(1 for x in spans if x["daysToConflict"] < 200)


def test_vegetation_is_deterministic(client):
    a = client.get("/api/vegetation/hotspots").json()["hotspots"]
    b = client.get("/api/vegetation/hotspots").json()["hotspots"]
    assert [c["hotspotScore"] for c in a] == [c["hotspotScore"] for c in b]
