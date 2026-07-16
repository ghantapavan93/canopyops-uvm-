"""Live change stream (SSE) — the push path behind the Command Center."""
from conftest import auth

from app.api import events
from app.core.security import tenant_from_authorization


def _tenant(client, email: str) -> str:
    return tenant_from_authorization(auth(client, email)["Authorization"])


def _corridor_id(client):
    return client.get("/api/corridors").json()[0]["id"]


def _square(cx=-83.19, cy=40.11, s=0.004):
    return {
        "type": "Polygon",
        "coordinates": [[[cx, cy], [cx + s, cy], [cx + s, cy + s], [cx, cy + s], [cx, cy]]],
    }


def _plan_body(cid):
    return {
        "corridorId": cid,
        "priority": "elevated",
        "targetCondition": "Restore MVCD clearance and establish compatible cover.",
        "methodCategory": "mechanical",
        "requiredEvidence": ["photo_before", "photo_after"],
        "verificationWindowDays": 30,
        "cycle": "mid_cycle",
        "dueInDays": 14,
        "plannedGeometry": _square(),
    }


def test_stream_opens_greets_and_closes(client, monkeypatch):
    """The endpoint streams text/event-stream, greets immediately (so the client
    can stand down its polling fallback), and ends on its own — the bounded
    lifetime that stops zombie connections from accumulating."""
    monkeypatch.setattr(events, "_POLL_SECONDS", 0.01)
    monkeypatch.setattr(events, "_MAX_STREAM_SECONDS", 0.05)

    with client.stream("GET", "/api/events/stream") as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        # nginx must not buffer the stream, or nothing ever reaches the browser.
        assert res.headers.get("x-accel-buffering") == "no"
        frames = list(res.iter_lines())

    assert any(f.startswith("event: hello") for f in frames)
    assert any(f.startswith("event: bye") for f in frames)


def test_watermark_changes_when_data_changes(client):
    """The watermark is what tells connected clients to refetch — it must move
    when a plan is created, or the board goes stale."""
    tenant = _tenant(client, "manager@synthetic.test")
    events._cache.clear()
    before = events.watermark(tenant)

    res = client.post(
        "/api/plans",
        json=_plan_body(_corridor_id(client)),
        headers=auth(client, "manager@synthetic.test"),
    )
    assert res.status_code == 201, res.text

    events._cache.clear()  # bypass the one-interval cache
    assert events.watermark(tenant) != before


def test_watermark_is_cached_per_interval(client, monkeypatch):
    """N connected clients must cost ONE query per interval, not N — that is the
    whole reason this is push instead of per-client polling."""
    tenant = _tenant(client, "manager@synthetic.test")
    events._cache.clear()
    first = events.watermark(tenant)

    calls = {"n": 0}
    real = events._read_watermark

    def counting(t):
        calls["n"] += 1
        return real(t)

    monkeypatch.setattr(events, "_read_watermark", counting)
    for _ in range(5):
        assert events.watermark(tenant) == first
    assert calls["n"] == 0  # all served from the cached interval


def test_watermark_is_tenant_scoped(client):
    """One program's activity must not invalidate another program's clients."""
    demo = _tenant(client, "manager@synthetic.test")
    ng = _tenant(client, "ng.manager@synthetic.test")
    assert demo != ng
    events._cache.clear()
    assert events.watermark(demo) != events.watermark(ng)
