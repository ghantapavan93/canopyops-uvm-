"""SQLAlchemy engine, session factory, and declarative base.

The engine is tuned for reliability under load: a bounded connection pool with
pre-ping (survives Postgres restarts / idle drops), periodic recycling (dodges
stale sockets behind proxies), and a server-side ``statement_timeout`` so a
runaway query is cancelled by Postgres instead of pinning a pooled connection.
``build_engine`` is parametrisable so tests can exercise those bounds directly.
"""
from collections.abc import Iterator

from fastapi import HTTPException
from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import DisconnectionError, InterfaceError, OperationalError
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.circuit import db_breaker
from app.core.config import get_settings

_settings = get_settings()


def build_engine(
    url: str | None = None,
    *,
    statement_timeout_ms: int | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_recycle_s: int | None = None,
) -> Engine:
    """Create a tuned engine. Any argument left as ``None`` falls back to the
    configured setting, so production uses config while tests can override a
    single knob (e.g. a tiny statement_timeout) without touching the rest."""
    s = _settings
    url = url or s.database_url
    timeout = s.db_statement_timeout_ms if statement_timeout_ms is None else statement_timeout_ms

    connect_args: dict = {}
    # Postgres-only: enforce the per-statement ceiling at the server.
    if url.startswith("postgresql") and timeout and timeout > 0:
        connect_args["options"] = f"-c statement_timeout={int(timeout)}"

    return create_engine(
        url,
        pool_pre_ping=True,  # survive Postgres restarts / idle drops
        pool_size=s.db_pool_size if pool_size is None else pool_size,
        max_overflow=s.db_max_overflow if max_overflow is None else max_overflow,
        pool_recycle=s.db_pool_recycle_s if pool_recycle_s is None else pool_recycle_s,
        connect_args=connect_args,
        future=True,
    )


engine = build_engine()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

# Install the multi-tenant read filter + insert stamp on the Session class.
from app.core.tenancy import register_tenant_guards  # noqa: E402

register_tenant_guards()


def pool_status() -> dict:
    """A snapshot of the connection pool for the health surface."""
    pool = engine.pool
    getters = ("size", "checkedin", "checkedout", "overflow")
    stats = {name: getattr(pool, name)() for name in getters if hasattr(pool, name)}
    stats["statement_timeout_ms"] = _settings.db_statement_timeout_ms
    return stats


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


# Connection-level failures that should trip the breaker (a browning-out DB),
# as opposed to app/client errors (IntegrityError, etc.) which must NOT.
_DB_OUTAGE_ERRORS = (OperationalError, InterfaceError, DisconnectionError)


def get_db() -> Iterator["SessionLocal"]:
    """FastAPI dependency yielding a request-scoped session, guarded by a circuit
    breaker. When the DB is browning out the breaker OPENs and this fails fast
    with 503 instead of every request waiting for a connection timeout."""
    if not db_breaker.allow():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "db_unavailable",
                "message": "The database is temporarily unavailable (circuit open). Retry shortly.",
            },
            headers={"Retry-After": "5"},
        )
    db = SessionLocal()
    try:
        yield db
        db_breaker.record_success()
    except _DB_OUTAGE_ERRORS:
        db_breaker.record_failure()
        raise
    finally:
        db.close()
