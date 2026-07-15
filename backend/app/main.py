"""CanopyOps Treatment Assurance API — application entrypoint.

Structured error envelope + correlation IDs are attached to every response so
the front end (and the Engineering Evidence route) can show real failure detail
instead of a spinner.
"""
import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import math

from app.core.concurrency import limiter
from app.core.logging import setup_logging
from app.core.metrics import metrics
from app.core.ratelimit import rate_limiter

from app.api import (
    auth,
    executions,
    geo_reference,
    health,
    integration,
    observability,
    odata,
    overview,
    plans,
    reliability,
    reports,
    risk,
    stewardship,
    terrain,
    treatments,
    vegetation,
    verifications,
)
from app.core.config import get_settings

settings = get_settings()
setup_logging()
logger = logging.getLogger("canopyops")

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Independent UVM treatment-assurance prototype. Not affiliated with or "
        "endorsed by The Davey Tree Expert Company. All data is synthetic.\n\n"
        "This is the live, typed integration contract — the seam a utility would "
        "integrate against (GIS, work-order/EAM, field sync)."
    ),
    # Serve docs under /api so they're reachable through the nginx /api proxy.
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Correlation-Id"],
)


# Probes must answer even while the app is shedding load, so orchestrators can
# still tell "overloaded" (shed 503s) apart from "unhealthy" (process/DB down).
_SHED_EXEMPT = {"/api/health", "/api/ready"}


def _client_key(request: Request) -> str:
    """Identify the caller for per-client limits. Trust the first X-Forwarded-For
    hop when present (the nginx web tier sets it), else the socket peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Attach a correlation id, apply per-client rate limiting then global
    load-shedding, time the request, emit a structured access log, and record it
    to the metrics registry."""
    correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id

    exempt = request.url.path in _SHED_EXEMPT

    # 1) Per-client rate limit (429) — before consuming a global slot, so a noisy
    #    client can't crowd out everyone else's capacity.
    if not exempt:
        allowed, retry_after = rate_limiter.check(_client_key(request))
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "code": "rate_limited",
                    "message": "Too many requests. Slow down and retry.",
                    "correlation_id": correlation_id,
                },
                headers={
                    "Retry-After": str(max(1, math.ceil(retry_after))),
                    "X-Correlation-Id": correlation_id,
                },
            )

    # 2) Global in-flight cap (503 load-shed).
    admitted = exempt or limiter.try_acquire()
    if not admitted:
        # Deliberate, self-protective 503 — not a server fault, so it's counted
        # separately from 5xx errors and carries a Retry-After for well-behaved
        # clients (the Angular sync outbox already backs off and retries).
        return JSONResponse(
            status_code=503,
            content={
                "code": "overloaded",
                "message": "The service is shedding load to stay responsive. Retry shortly.",
                "correlation_id": correlation_id,
            },
            headers={"Retry-After": "1", "X-Correlation-Id": correlation_id},
        )

    start = time.perf_counter()
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:  # noqa: BLE001 — convert to structured envelope
        status = 500
        logger.exception(
            "unhandled_error", extra={"correlation_id": correlation_id, "path": request.url.path}
        )
        response = JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "Unexpected server error",
                "correlation_id": correlation_id,
            },
        )
    finally:
        if not exempt:
            limiter.release()

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    route = request.scope.get("route")
    endpoint = f"{request.method} {getattr(route, 'path', request.url.path)}"
    metrics.record(endpoint, status, duration_ms)
    logger.info(
        "request",
        extra={
            "correlation_id": correlation_id,
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "duration_ms": duration_ms,
        },
    )
    response.headers["X-Correlation-Id"] = correlation_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return the same structured envelope for 422 validation errors."""
    safe_errors = [
        {"loc": list(e.get("loc", [])), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "Request validation failed",
            "correlation_id": getattr(request.state, "correlation_id", None),
            "errors": safe_errors,
        },
    )


app.include_router(health.router, prefix="/api")
app.include_router(observability.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(geo_reference.router, prefix="/api")
app.include_router(treatments.router, prefix="/api")
app.include_router(executions.router, prefix="/api")
app.include_router(plans.router, prefix="/api")
app.include_router(verifications.router, prefix="/api")
app.include_router(overview.router, prefix="/api")
app.include_router(stewardship.router, prefix="/api")
app.include_router(integration.router, prefix="/api")
app.include_router(odata.router, prefix="/api")
app.include_router(terrain.router, prefix="/api")
app.include_router(risk.router, prefix="/api")
app.include_router(reliability.router, prefix="/api")
app.include_router(vegetation.router, prefix="/api")
app.include_router(reports.router, prefix="/api")


@app.get("/api")
def root() -> dict:
    return {
        "service": "canopyops-api",
        "version": "0.1.0",
        "docs": "/docs",
        "notice": "Synthetic prototype. Not affiliated with The Davey Tree Expert Company.",
    }
