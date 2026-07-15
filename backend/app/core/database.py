"""SQLAlchemy engine, session factory, and declarative base.

The engine is tuned for reliability under load: a bounded connection pool with
pre-ping (survives Postgres restarts / idle drops), periodic recycling (dodges
stale sockets behind proxies), and a server-side ``statement_timeout`` so a
runaway query is cancelled by Postgres instead of pinning a pooled connection.
``build_engine`` is parametrisable so tests can exercise those bounds directly.
"""
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

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


def pool_status() -> dict:
    """A snapshot of the connection pool for the health surface."""
    pool = engine.pool
    getters = ("size", "checkedin", "checkedout", "overflow")
    stats = {name: getattr(pool, name)() for name in getters if hasattr(pool, name)}
    stats["statement_timeout_ms"] = _settings.db_statement_timeout_ms
    return stats


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db() -> Iterator["SessionLocal"]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
