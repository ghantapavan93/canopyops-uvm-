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
    # One WBS element per seeded plan — derived so the invariant survives the
    # demo data growing (a literal here broke when the golden record landed).
    seeded = len(client.get("/api/treatments", params={"limit": 500}).json())
    res = client.get("/api/odata/WbsElements?$top=2&$count=true&$select=Wbs,Status")
    body = res.json()
    assert body["@odata.count"] == seeded
    assert len(body["value"]) == 2            # server-driven page window
    # The next link points at this entity set and advances the window. Its exact
    # parameter ORDER is not the contract (it now carries every active option —
    # see test_next_link_is_actually_followable), so don't assert a prefix.
    nxt = body["@odata.nextLink"]
    assert nxt.startswith("WbsElements?") and "$skip=2" in nxt, nxt
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
    """Parentheses must change the meaning, and `and` must bind tighter than `or`.

    Asserts the PROPERTY rather than a literal set of ids: naming the exact rows
    couples an operator-precedence test to the seed, and it broke the moment the
    demo territory grew. What matters is the relationship between the two results.
    """
    def wbs(f: str) -> set[str]:
        rows = client.get(f"/api/odata/WbsElements?$filter={f}&$select=Wbs,Status,Priority").json()["value"]
        return {r["Wbs"] for r in rows}

    def rows(f: str) -> list[dict]:
        return client.get(f"/api/odata/WbsElements?$filter={f}&$select=Wbs,Status,Priority").json()["value"]

    grouped = rows("(Status eq 'draft' or Status eq 'applied') and Priority eq 'hazard'")
    # The parenthesised form is an AND against hazard — nothing else can appear.
    assert grouped, "expected at least one draft/applied hazard span in the seed"
    for r in grouped:
        assert r["Priority"] == "hazard"
        assert r["Status"] in ("draft", "applied")

    # Unparenthesised, `and` binds tighter: draft OR (applied AND hazard). So the
    # result is a strict SUPERSET — it also admits drafts that are not hazards.
    ungrouped = rows("Status eq 'draft' or Status eq 'applied' and Priority eq 'hazard'")
    g, u = {r["Wbs"] for r in grouped}, {r["Wbs"] for r in ungrouped}
    assert g < u, "precedence changed nothing — `and` is not binding tighter than `or`"
    assert any(r["Status"] == "draft" and r["Priority"] != "hazard" for r in ungrouped), (
        "the unparenthesised form should admit non-hazard drafts"
    )


def test_etag_conditional_request_returns_304(client):
    first = client.get("/api/odata/CatsEntries")
    etag = first.headers.get("ETag")
    assert etag, "collection response must carry an ETag"

    again = client.get("/api/odata/CatsEntries", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.headers.get("ETag") == etag


def test_batch_bundles_reads_in_one_round_trip(client):
    seeded = len(client.get("/api/treatments", params={"limit": 500}).json())
    res = client.post("/api/odata/$batch", json={"requests": [
        {"id": "wbs", "method": "GET", "url": "WbsElements?$top=2&$count=true"},
        {"id": "cats", "method": "GET", "url": "CatsEntries?$filter=Confirmed eq true"},
    ]})
    assert res.status_code == 200
    responses = {r["id"]: r for r in res.json()["responses"]}
    assert responses["wbs"]["status"] == 200
    assert responses["wbs"]["body"]["@odata.count"] == seeded
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


def test_paging_tolerates_malformed_top_skip(client):
    # $top=abc / $skip=-3 must fall back to defaults, not 500
    res = client.get("/api/odata/WbsElements?$top=abc&$skip=-3")
    assert res.status_code == 200
    assert len(res.json()["value"]) <= 5   # default page window


def test_batch_rejects_writes_read_only_facade(client):
    res = client.post("/api/odata/$batch", json={"requests": [
        {"id": "w", "method": "POST", "url": "WbsElements"},
    ]})
    assert res.json()["responses"][0]["status"] == 501


def test_next_link_is_actually_followable(client):
    """@odata.nextLink must carry the whole query, not just the paging.

    A spec-compliant client follows the link VERBATIM. If it only carries
    $skip/$top, page 2 comes back from a different (unfiltered, unsorted) result
    set than page 1 — which surfaces much later as "the totals don't reconcile".
    """
    q = ("WbsElements?$filter=Priority eq 'routine'&$orderby=Wbs asc"
         "&$select=Wbs,Priority&$top=2&$count=true")
    first = client.get(f"/api/odata/{q}").json()
    nxt = first.get("@odata.nextLink")
    assert nxt, "expected a next link — seed should have >2 routine spans"

    # Every option survives the round trip.
    for opt in ("$filter=", "$orderby=", "$select=", "$top=", "$count="):
        assert opt in nxt, f"{opt} was dropped from the next link: {nxt}"

    # Follow it verbatim, exactly as a client would.
    second = client.get(f"/api/odata/{nxt}").json()
    assert second["@odata.count"] == first["@odata.count"], "paging changed the result set"
    # The filter still holds, and $select is still honoured.
    for row in second["value"]:
        assert row["Priority"] == "routine"
        assert set(row) - {"CatsEntries@odata.navigationLink"} == {"Wbs", "Priority"}
    # It is genuinely the NEXT page, not the same one.
    assert {r["Wbs"] for r in second["value"]}.isdisjoint({r["Wbs"] for r in first["value"]})
