"""3D terrain — synthetic DEM grid + corridor elevation/slope profile."""
from __future__ import annotations


def test_terrain_grid_shape_and_relief(client):
    res = client.get("/api/geo/terrain?cols=40&rows=24")
    assert res.status_code == 200
    assert res.headers.get("ETag")
    body = res.json()
    assert body["cols"] == 40 and body["rows"] == 24
    assert len(body["elevations"]) == 24
    assert all(len(row) == 40 for row in body["elevations"])
    assert body["maxElev"] > body["minElev"]        # there is real relief
    assert body["bbox"][0] < body["bbox"][2]


def test_terrain_grid_conditional_304(client):
    etag = client.get("/api/geo/terrain?cols=40&rows=24").headers["ETag"]
    again = client.get("/api/geo/terrain?cols=40&rows=24", headers={"If-None-Match": etag})
    assert again.status_code == 304


def test_terrain_profile_computes_gain_and_slope(client):
    # A line climbing toward the ridge/hill region of the sandbox.
    line = {"type": "LineString", "coordinates": [[-83.19, 40.103], [-83.16, 40.118]]}
    res = client.post("/api/geo/terrain/profile", json={"geometry": line, "samples": 40}).json()
    assert len(res["points"]) == 40
    assert res["lengthM"] > 0
    assert res["maxSlopePct"] >= 0
    # elevation series is populated and varies across the traverse
    elevs = [p["elevationM"] for p in res["points"]]
    assert max(elevs) > min(elevs)


def test_terrain_profile_handles_degenerate_line(client):
    line = {"type": "LineString", "coordinates": [[-83.19, 40.11]]}
    res = client.post("/api/geo/terrain/profile", json={"geometry": line}).json()
    assert res["points"] == []
    assert res["lengthM"] == 0
