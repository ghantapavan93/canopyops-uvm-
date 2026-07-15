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


@lru_cache
def get_settings() -> Settings:
    return Settings()
