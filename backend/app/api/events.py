"""Live change stream (Server-Sent Events).

Replaces the Command Center's per-client 12s poll with server push. The stream
carries an *invalidation* signal, not the data: when a program's treatment data
changes, connected clients are told to refetch the page they're actually looking
at. That keeps the payload tiny and reuses the existing (filtered, paged,
tenant-scoped) read path instead of duplicating it as a delta protocol.

Why a server-side watermark rather than an in-process pub/sub: mutations arrive
from the API *and* the background worker (separate containers), so an in-process
event bus would miss the worker's writes and would need Redis to fan out across
replicas. A cheap watermark query is correct for every writer, and the result is
cached per program so N connected clients cost ONE query per interval — not N.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from app.core.database import SessionLocal
from app.core.tenancy import reset_current_tenant, set_current_tenant

router = APIRouter(prefix="/events", tags=["events"])
logger = logging.getLogger("canopyops")

# How often the server re-checks for changes, and how often we emit a comment
# frame to stop idle proxies from closing the connection.
_POLL_SECONDS = 2.0
_KEEPALIVE_SECONDS = 15.0

# Bounded connection lifetime. A stream that never ends leaves zombie
# connections behind whenever a client vanishes without a clean close (phone
# sleeps, laptop lid shuts, NAT drops the flow) and pins every viewer to the
# replica they first hit. Closing periodically lets the client reconnect —
# which it already does with backoff — and lets the fleet rebalance.
_MAX_STREAM_SECONDS = 900.0

# Watermark cache, shared by every client on the same program.
_cache: dict[str, tuple[float, str]] = {}
_cache_lock = threading.Lock()


def _read_watermark(tenant: str | None) -> str:
    """A cheap change token for one program's treatment data.

    Opens a SHORT-LIVED session per check. A stream must never hold a pooled
    connection for its lifetime — a handful of viewers would exhaust the pool.
    """
    token = set_current_tenant(tenant)
    try:
        with SessionLocal() as db:
            row = db.execute(
                text(
                    "SELECT count(*), coalesce(max(updated_at), 'epoch') "
                    "FROM treatment_plan WHERE tenant_id = :t"
                ),
                {"t": tenant},
            ).one()
        return f"{row[0]}:{row[1]}"
    finally:
        reset_current_tenant(token)


def watermark(tenant: str | None) -> str:
    """Watermark for `tenant`, cached for one poll interval so that N connected
    clients cost one DB query per interval rather than N."""
    key = tenant or ""
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _POLL_SECONDS:
            return hit[1]
    value = _read_watermark(tenant)
    with _cache_lock:
        _cache[key] = (time.monotonic(), value)
    return value


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    """SSE stream of change notifications for the caller's program."""
    # Capture the tenant NOW. The tenant ContextVar is reset as soon as the
    # middleware returns this response, but the body generator below runs
    # afterwards — reading it lazily would resolve to the wrong (or no) program.
    tenant = getattr(request.state, "tenant", None)

    async def gen():
        last: str | None = None
        idle = 0.0
        started = time.monotonic()
        # Greet immediately so the client knows push is live and can stand down
        # its polling fallback.
        yield "event: hello\ndata: {}\n\n"
        while True:
            if await request.is_disconnected():
                break
            if time.monotonic() - started >= _MAX_STREAM_SECONDS:
                # Bounded lifetime — the client reconnects with backoff.
                yield "event: bye\ndata: {}\n\n"
                break
            try:
                # Off the event loop: the watermark uses a sync DB session.
                current = await asyncio.to_thread(watermark, tenant)
            except Exception:  # noqa: BLE001 — a DB blip must not kill the stream
                logger.warning("sse_watermark_failed", exc_info=True)
                current = last
            if current is not None and current != last:
                first = last is None
                last = current
                # The first read only establishes a baseline — the client just
                # loaded this data, so don't make it refetch immediately.
                if not first:
                    yield (
                        "event: treatments.changed\n"
                        f"data: {json.dumps({'watermark': current})}\n\n"
                    )
                idle = 0.0
            else:
                idle += _POLL_SECONDS
                if idle >= _KEEPALIVE_SECONDS:
                    idle = 0.0
                    yield ": keepalive\n\n"
            await asyncio.sleep(_POLL_SECONDS)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Tell nginx not to buffer this response, or nothing ever flushes.
            "X-Accel-Buffering": "no",
        },
    )
