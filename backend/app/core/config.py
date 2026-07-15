"""Runtime configuration, loaded from environment (12-factor)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CanopyOps Treatment Assurance API"
    environment: str = "local"

    # Database (PostGIS). Overridden by docker-compose in the container network.
    database_url: str = (
        "postgresql+psycopg2://canopyops:canopyops@localhost:5432/canopyops"
    )

    # --- Connection pool + query-time bounds (reliability under load) ---------
    # Each worker owns a pool of this size; max_overflow bursts above it briefly.
    # Size so (workers × (pool + overflow)) stays under Postgres' max_connections.
    db_pool_size: int = 5
    db_max_overflow: int = 10
    # Recycle connections older than this (seconds) to dodge stale-socket drops.
    db_pool_recycle_s: int = 1800
    # Server-side per-statement ceiling (ms): a runaway query is cancelled instead
    # of pinning a pooled connection forever. 0 disables. Applied via psycopg2
    # `options=-c statement_timeout=…` so it's enforced by Postgres, not the app.
    db_statement_timeout_ms: int = 15000

    # --- Overload protection (graceful load-shedding) -------------------------
    # Max requests in flight per worker before we shed with 503 + Retry-After,
    # rather than letting the event loop and pool collapse under a thundering
    # herd. 0 disables the cap. Health/readiness probes are always exempt.
    max_concurrent_requests: int = 64

    # --- Per-client rate limiting (token bucket) ------------------------------
    # Protects the service from a single noisy client (distinct from the global
    # load-shedder above). Each client refills `rate_limit_per_min` tokens/min
    # and may burst up to `rate_limit_burst`; over that → 429 + Retry-After.
    rate_limit_enabled: bool = True
    rate_limit_per_min: int = 240
    rate_limit_burst: int = 60

    # --- Database circuit breaker ---------------------------------------------
    # After this many consecutive DB errors the breaker OPENS and DB-backed
    # requests fail fast with 503 (instead of each waiting for a connection
    # timeout); after reset_timeout_s it probes once and closes on success.
    db_breaker_enabled: bool = True
    db_breaker_failure_threshold: int = 5
    db_breaker_reset_timeout_s: float = 10.0

    # --- Horizontal scale -----------------------------------------------------
    # Uvicorn worker processes. The API is stateless (session-per-request; all
    # shared state lives in Postgres), so this scales across cores/replicas with
    # no sticky sessions. Note: the in-process metrics registry is per-worker, so
    # >1 worker fragments /api/metrics (a real deployment scrapes each worker).
    web_concurrency: int = 1

    # Synthetic JWT auth. NOT a real secret; the prototype issues its own tokens
    # for synthetic users only. Never reuse in production.
    jwt_secret: str = "synthetic-dev-secret-not-for-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720

    # CORS origin for the Angular dev/prod container.
    frontend_origin: str = "http://localhost:4200"

    # --- OpenTelemetry (distributed tracing) ----------------------------------
    # Real spans across request → DB with W3C trace-context propagation. The
    # trace_id rides on every structured log line, error envelope, and the
    # X-Trace-Id response header. Export to an OTLP collector when an endpoint is
    # set; console export is opt-in (noisy) for local inspection.
    otel_enabled: bool = True
    otel_service_name: str = "canopyops-api"
    otel_console_export: bool = False
    otel_exporter_otlp_endpoint: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
