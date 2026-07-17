"""Runtime configuration, loaded from environment (12-factor)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CanopyOps Treatment Assurance API"
    environment: str = "local"

    # Database (PostGIS). Overridden by docker-compose in the container network.
    # `database_url` is the APP connection — a non-superuser role so Postgres
    # Row-Level Security actually applies (superusers bypass RLS). Migrations and
    # seeding use `admin_database_url` (the owner/superuser); when unset it falls
    # back to database_url (single-role dev without RLS enforcement).
    database_url: str = (
        "postgresql+psycopg2://canopyops:canopyops@localhost:5432/canopyops"
    )
    admin_database_url: str | None = None

    @property
    def effective_admin_url(self) -> str:
        return self.admin_database_url or self.database_url

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

    # A job stuck in 'running' longer than this (a worker died mid-job) is reaped
    # to a terminal 'failed' — never left running forever.
    job_stuck_timeout_s: int = 300

    # Drain the job queue on a daemon thread INSIDE the API process instead of a
    # dedicated worker container. A deliberate downgrade for hosts whose free
    # tier offers no background-service type (e.g. Render free), where the only
    # alternative is that queued jobs never run at all. Off by default: the real
    # topology is a separate worker. Prefer web_concurrency=1 when enabling this,
    # or every uvicorn worker starts its own redundant poller.
    run_worker_in_process: bool = False

    # Allows POST /api/demo/reset to re-seed the synthetic demonstration data so
    # a reviewer can restore the golden record after clicking around. Guarded by
    # a flag so it can never become a "wipe the database" button on real data.
    demo_reset_enabled: bool = True

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

    # --- Evidence object storage (S3 / MinIO) ---------------------------------
    # Evidence files live in object storage, not the DB. "memory" is an in-process
    # fake for tests; "s3" talks to MinIO/S3 with presigned upload URLs so bytes
    # go client → storage directly (the API never proxies the file).
    storage_backend: str = "memory"            # memory | s3
    storage_endpoint: str = "http://minio:9000"
    storage_access_key: str = "canopyops"
    storage_secret_key: str = "canopyops-secret"
    storage_bucket: str = "evidence"
    storage_region: str = "us-east-1"
    storage_url_expiry_s: int = 900            # presigned-URL lifetime

    # Evidence validation + upload throttling.
    evidence_max_bytes: int = 15_000_000       # 15 MB per file
    evidence_allowed_types: str = "image/jpeg,image/png,image/webp,application/pdf"
    upload_rate_per_min: int = 60              # stricter than the general API limit
    upload_rate_burst: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
