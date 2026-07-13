"""Tests for the analytics + module endpoints added after the core lifecycle:
plan creation (with geometry validation & RBAC), the program overview period
selector, the stewardship real-data signals, and the encroachment choropleth.
"""
from conftest import auth


def _corridor_id(client):
    return client.get("/api/corridors").json()[0]["id"]


def _square(cx=-83.19, cy=40.11, s=0.004):
    return {
        "type": "Polygon",
        "coordinates": [[[cx, cy], [cx + s, cy], [cx + s, cy + s], [cx, cy + s], [cx, cy]]],
    }


def _plan_body(cid, geometry):
    return {
        "corridorId": cid,
        "priority": "elevated",
        "targetCondition": "Restore MVCD clearance and establish compatible cover.",
        "methodCategory": "mechanical",
        "requiredEvidence": ["photo_before", "photo_after"],
        "verificationWindowDays": 30,
        "cycle": "mid_cycle",
        "dueInDays": 14,
        "plannedGeometry": geometry,
    }


# --- Treatment Plan Builder ---
def test_manager_creates_plan(client):
    cid = _corridor_id(client)
    res = client.post("/api/plans", json=_plan_body(cid, _square()),
                      headers=auth(client, "manager@synthetic.test"))
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "scheduled"
    assert body["workOrderRef"].startswith("WO-2026-")
    assert body["methodCategory"] == "mechanical"


def test_create_plan_rejects_self_intersecting_polygon(client):
    cid = _corridor_id(client)
    bowtie = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}
    res = client.post("/api/plans", json=_plan_body(cid, bowtie),
                      headers=auth(client, "manager@synthetic.test"))
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "invalid_geometry"


def test_create_plan_rbac_field_crew_forbidden(client):
    cid = _corridor_id(client)
    res = client.post("/api/plans", json=_plan_body(cid, _square()),
                      headers=auth(client, "crew@synthetic.test"))
    assert res.status_code == 403


def test_create_plan_unknown_corridor_404(client):
    res = client.post("/api/plans", json=_plan_body("does-not-exist", _square()),
                      headers=auth(client, "manager@synthetic.test"))
    assert res.status_code == 404


# --- Program Overview period selector ---
def test_overview_period_shapes(client):
    for period, n in [("ytd", 12), ("quarter", 6), ("cycle", 5)]:
        d = client.get("/api/overview", params={"period": period}).json()
        assert len(d["plannedSpans"]) == n
        assert len(d["weeks"]) == n
        assert len(d["completedSpans"]) == n


def test_overview_evidence_tile_reflects_real_records(client):
    d = client.get("/api/overview").json()
    assert d["realPlanCount"] >= 1
    assert any(t["key"] == "evidence" for t in d["tiles"])


# --- Stewardship (real signals) ---
def test_stewardship_method_mix_sums_to_plan_count(client):
    d = client.get("/api/stewardship").json()
    total_methods = sum(s["points"][0] for s in d["methodMix"])
    assert total_methods == d["realPlanCount"]


def test_stewardship_reports_real_constraint_intersections(client):
    d = client.get("/api/stewardship").json()
    hftd = next((c for c in d["constraints"] if c["category"] == "hftd"), None)
    assert hftd is not None
    # The synthetic HFTD district overlaps at least one planned polygon.
    assert hftd["intersectingPlans"] >= 1


# --- Geometry analysis (constraint-aware planning) ---
def test_geo_analyze_reports_area_and_constraint_intersection(client):
    recs = client.get("/api/treatments").json()
    hftd_plan = next(r for r in recs if "hftd" in r["constraintFlags"])
    res = client.post("/api/geo/analyze", json={"geometry": hftd_plan["plannedGeometry"]})
    body = res.json()
    assert body["valid"] is True
    assert body["areaAcres"] > 0
    assert any(c["category"] == "hftd" for c in body["intersectingConstraints"])


def test_geo_analyze_rejects_invalid_polygon(client):
    bowtie = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]}
    body = client.post("/api/geo/analyze", json={"geometry": bowtie}).json()
    assert body["valid"] is False
    assert body["areaAcres"] == 0
    assert body["intersectingConstraints"] == []


# --- Encroachment choropleth ---
def test_encroachments_deterministic(client):
    a = client.get("/api/encroachments").json()
    b = client.get("/api/encroachments").json()
    assert len(a["regions"]) == 8
    assert a["totalEncroachments"] == b["totalEncroachments"]  # stable across reloads
    assert a["maxEncroachments"] == max(r["encroachments"] for r in a["regions"])
    # every region carries a valid polygon
    assert all(r["geometry"]["type"] == "Polygon" for r in a["regions"])


# --- Integration surfaces ---
def test_openapi_contract_is_served(client):
    spec = client.get("/api/openapi.json")
    assert spec.status_code == 200
    body = spec.json()
    assert body["info"]["title"]
    assert "/api/import/corridors" in body["paths"]  # integration path documented


def test_import_corridors_from_geojson(client):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"circuitId": "CKT-9001", "spanLabel": "SPAN 1-2", "name": "Imported", "voltageKv": 138},
                "geometry": {"type": "LineString", "coordinates": [[-83.05, 40.02], [-83.04, 40.03]]},
            },
            {  # non-LineString → skipped, not fatal
                "type": "Feature", "properties": {},
                "geometry": {"type": "Point", "coordinates": [0, 0]},
            },
        ],
    }
    res = client.post("/api/import/corridors", json=fc, headers=auth(client, "manager@synthetic.test"))
    assert res.status_code == 200
    body = res.json()
    assert body["imported"] == 1 and body["skipped"] == 1
    circuits = [c["circuitId"] for c in client.get("/api/corridors").json()]
    assert "CKT-9001" in circuits


def test_import_corridors_requires_manager(client):
    res = client.post(
        "/api/import/corridors",
        json={"type": "FeatureCollection", "features": []},
        headers=auth(client, "crew@synthetic.test"),
    )
    assert res.status_code == 403


# --- Observability + API consistency ---
def test_metrics_endpoint_reports_counts_and_latency(client):
    client.get("/api/health")  # generate at least one request
    m = client.get("/api/metrics").json()
    assert m["total_requests"] >= 1
    assert "p95" in m["latency_ms"]
    assert isinstance(m["endpoints"], list)


def test_validation_errors_use_structured_envelope(client):
    # missing required fields → structured 422 (not FastAPI's default shape)
    res = client.post(
        "/api/plans", json={"corridorId": "x"}, headers=auth(client, "manager@synthetic.test")
    )
    assert res.status_code == 422
    assert res.json()["code"] == "validation_error"


def test_treatments_pagination_limit(client):
    rows = client.get("/api/treatments", params={"limit": 2}).json()
    assert len(rows) <= 2
