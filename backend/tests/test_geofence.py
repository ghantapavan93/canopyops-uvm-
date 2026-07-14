"""Geofence proximity alerts — verifies the PostGIS-backed escalation
(clear -> warning -> entered/breach) that powers the field-safety map.

Seeded water buffer (BLOCKING) spans roughly lon [-83.18, -83.16], lat
[40.108, 40.116] in the synthetic sandbox."""
from __future__ import annotations

INSIDE = {"lon": -83.17, "lat": 40.112}          # inside the blocking water buffer
NEAR = {"lon": -83.182, "lat": 40.112}           # ~170 m west of the buffer edge
FAR = {"lon": -83.0, "lat": 40.0}                # kilometres away


def test_inside_blocking_zone_is_a_breach(client):
    res = client.post("/api/geo/proximity", json={**INSIDE, "warningMeters": 60}).json()
    assert res["overallLevel"] == "breach"
    nearest = res["zones"][0]
    assert nearest["inside"] is True
    assert nearest["distanceM"] == 0.0
    assert nearest["severity"] == "blocking"
    assert "STOP" in nearest["action"]


def test_near_zone_raises_a_warning(client):
    res = client.post("/api/geo/proximity", json={**NEAR, "warningMeters": 300}).json()
    nearest = res["zones"][0]
    assert nearest["inside"] is False
    assert 0 < nearest["distanceM"] <= 300
    assert nearest["level"] == "warning"
    assert res["overallLevel"] == "warning"


def test_far_position_is_clear(client):
    res = client.post("/api/geo/proximity", json={**FAR, "warningMeters": 60}).json()
    assert res["overallLevel"] == "clear"
    assert all(z["level"] == "clear" for z in res["zones"])


def test_zones_sorted_nearest_first(client):
    res = client.post("/api/geo/proximity", json={**FAR, "warningMeters": 60}).json()
    dists = [z["distanceM"] for z in res["zones"]]
    assert dists == sorted(dists)


def test_zones_snapshot_has_version_and_etag(client):
    res = client.get("/api/geo/zones")
    assert res.status_code == 200
    assert res.headers.get("ETag")
    body = res.json()
    assert body["version"]
    assert len(body["zones"]) == 3               # three seeded constraints
    assert all(z["geometry"] for z in body["zones"])  # geometry travels for offline use


def test_zones_snapshot_conditional_request_returns_304(client):
    etag = client.get("/api/geo/zones").headers["ETag"]
    again = client.get("/api/geo/zones", headers={"If-None-Match": etag})
    assert again.status_code == 304
