"""OData (SAP-style) integration surface — verifies the patterns the Davey
Angular role calls for: server paging, $count, $select, $filter, deferred
navigation vs $expand, and ETag/If-None-Match conditional caching."""
from __future__ import annotations


def test_metadata_and_service_document(client):
    svc = client.get("/api/odata/").json()
    names = {e["name"] for e in svc["value"]}
    assert {"WbsElements", "CatsEntries"} <= names

    meta = client.get("/api/odata/$metadata")
    assert meta.status_code == 200
    assert "application/xml" in meta.headers["content-type"]
    assert "<EntityType Name=\"WbsElement\">" in meta.text
    assert "NavigationProperty Name=\"CatsEntries\"" in meta.text


def test_paging_count_and_select(client):
    res = client.get("/api/odata/WbsElements?$top=2&$count=true&$select=Wbs,Status")
    body = res.json()
    assert body["@odata.count"] == 6          # six seeded plans -> six WBS elements
    assert len(body["value"]) == 2            # server-driven page window
    assert body["@odata.nextLink"].startswith("WbsElements?$skip=2")
    # $select is honoured (plus the deferred nav link), nothing else leaks.
    keys = set(body["value"][0]) - {"CatsEntries@odata.navigationLink"}
    assert keys == {"Wbs", "Status"}


def test_navigation_is_deferred_then_expanded(client):
    deferred = client.get("/api/odata/WbsElements?$select=Wbs").json()["value"][0]
    assert "CatsEntries@odata.navigationLink" in deferred   # link only, not data
    assert "CatsEntries" not in deferred

    expanded = client.get("/api/odata/WbsElements?$expand=CatsEntries").json()["value"]
    # At least one element has materialised CATS rows once expanded.
    assert any(isinstance(e.get("CatsEntries"), list) and e["CatsEntries"] for e in expanded)


def test_filter_subset(client):
    res = client.get(
        "/api/odata/WbsElements?$filter=Status eq 'awaiting_verification'"
    ).json()
    assert res["value"], "expected at least one awaiting record from the seed"
    assert all(r["Status"] == "awaiting_verification" for r in res["value"])


def test_filter_parenthesised_grouping_and_precedence(client):
    # Seeded: UVM.2026.1003 = applied + hazard; 1005 = draft + routine; 1006 = hazard.
    grouped = client.get(
        "/api/odata/WbsElements"
        "?$filter=(Status eq 'draft' or Status eq 'applied') and Priority eq 'hazard'"
        "&$select=Wbs"
    ).json()["value"]
    assert [r["Wbs"] for r in grouped] == ["UVM.2026.1003"]

    # Without parentheses, `and` binds tighter: draft OR (applied AND hazard) → 2 rows.
    ungrouped = client.get(
        "/api/odata/WbsElements"
        "?$filter=Status eq 'draft' or Status eq 'applied' and Priority eq 'hazard'"
        "&$select=Wbs"
    ).json()["value"]
    assert {r["Wbs"] for r in ungrouped} == {"UVM.2026.1003", "UVM.2026.1005"}


def test_etag_conditional_request_returns_304(client):
    first = client.get("/api/odata/CatsEntries")
    etag = first.headers.get("ETag")
    assert etag, "collection response must carry an ETag"

    again = client.get("/api/odata/CatsEntries", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.headers.get("ETag") == etag


def test_batch_bundles_reads_in_one_round_trip(client):
    res = client.post("/api/odata/$batch", json={"requests": [
        {"id": "wbs", "method": "GET", "url": "WbsElements?$top=2&$count=true"},
        {"id": "cats", "method": "GET", "url": "CatsEntries?$filter=Confirmed eq true"},
    ]})
    assert res.status_code == 200
    responses = {r["id"]: r for r in res.json()["responses"]}
    assert responses["wbs"]["status"] == 200
    assert responses["wbs"]["body"]["@odata.count"] == 6
    assert len(responses["wbs"]["body"]["value"]) == 2
    assert responses["cats"]["status"] == 200
    assert all(c["Confirmed"] for c in responses["cats"]["body"]["value"])


def test_batch_honours_query_options_and_entity_and_nav_routes(client):
    # discover a real key + its expected CATS count from the plain routes first
    key = client.get("/api/odata/WbsElements?$expand=CatsEntries").json()["value"][0]["Wbs"]
    res = client.post("/api/odata/$batch", json={"requests": [
        {"id": "1", "method": "GET", "url": f"WbsElements('{key}')"},
        {"id": "2", "method": "GET", "url": f"WbsElements('{key}')/CatsEntries"},
    ]})
    by_id = {r["id"]: r for r in res.json()["responses"]}
    assert by_id["1"]["body"]["Wbs"] == key
    assert all(c["Wbs"] == key for c in by_id["2"]["body"]["value"])


def test_batch_dependency_short_circuits_on_failure(client):
    res = client.post("/api/odata/$batch", json={"requests": [
        {"id": "bad", "method": "GET", "url": "WbsElements('NOPE.0000')"},
        {"id": "child", "method": "GET", "url": "CatsEntries", "dependsOn": ["bad"]},
    ]})
    by_id = {r["id"]: r for r in res.json()["responses"]}
    assert by_id["bad"]["status"] == 404
    assert by_id["child"]["status"] == 424        # skipped because its dependency failed


def test_batch_rejects_writes_read_only_facade(client):
    res = client.post("/api/odata/$batch", json={"requests": [
        {"id": "w", "method": "POST", "url": "WbsElements"},
    ]})
    assert res.json()["responses"][0]["status"] == 501
