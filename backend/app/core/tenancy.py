"""Multi-tenant (per-program) isolation.

Every program-owned row carries a ``tenant_id`` (a utility client / program). The
current tenant lives in a ``ContextVar`` set per request from the JWT, and two
SQLAlchemy Session hooks enforce isolation automatically:

* ``do_orm_execute`` adds ``with_loader_criteria(TenantScoped, tenant == current)``
  to **every** ORM SELECT — so a forgotten ``WHERE tenant_id`` can't leak data.
* ``before_flush`` stamps the current tenant onto any new tenant-scoped row.

When no tenant is set (background/admin context, or a raw seed) the filter is a
no-op — full access. See docs/MULTI-TENANCY.md; DB-level Row-Level Security is
documented there as the production defense-in-depth on top of this app-layer
guarantee.
"""
from __future__ import annotations

import contextvars

from sqlalchemy import String, event, text
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria

# The default program for the public demo + unauthenticated requests.
DEFAULT_TENANT = "demo"

_current_tenant: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_tenant", default=None
)


def set_current_tenant(tenant_id: str | None) -> contextvars.Token:
    return _current_tenant.set(tenant_id)


def reset_current_tenant(token: contextvars.Token) -> None:
    _current_tenant.reset(token)


def get_current_tenant() -> str | None:
    return _current_tenant.get()


class TenantScoped:
    """Mixin: gives a table a ``tenant_id`` and opts it into automatic scoping."""

    tenant_id: Mapped[str] = mapped_column(String, index=True)


def register_tenant_guards() -> None:
    """Install the Session-level read filter + insert stamp. Idempotent."""
    if getattr(register_tenant_guards, "_installed", False):
        return

    @event.listens_for(Session, "do_orm_execute")
    def _apply_tenant_filter(execute_state):  # noqa: ANN001
        if not execute_state.is_select:
            return
        if execute_state.execution_options.get("skip_tenant_filter"):
            return
        tenant = _current_tenant.get()
        if tenant is None:
            return
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                TenantScoped,
                lambda cls: cls.tenant_id == tenant,
                include_aliases=True,
            )
        )

    @event.listens_for(Session, "before_flush")
    def _stamp_tenant_on_insert(session, flush_context, instances):  # noqa: ANN001
        tenant = _current_tenant.get()
        if tenant is None:
            return
        for obj in session.new:
            if isinstance(obj, TenantScoped) and getattr(obj, "tenant_id", None) is None:
                obj.tenant_id = tenant

    @event.listens_for(Session, "after_begin")
    def _set_rls_guc(session, transaction, connection):  # noqa: ANN001
        """Push the current program into a transaction-local Postgres GUC that
        the Row-Level-Security policies read. Fires at the start of every
        transaction (including after a mid-request commit), so the GUC is always
        fresh; being transaction-local, it clears on commit so a pooled
        connection never carries a stale program. No-op off Postgres / when no
        program is set (RLS policies then fail closed — zero rows)."""
        tenant = _current_tenant.get()
        if tenant is None or connection.dialect.name != "postgresql":
            return
        connection.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant})

    register_tenant_guards._installed = True
