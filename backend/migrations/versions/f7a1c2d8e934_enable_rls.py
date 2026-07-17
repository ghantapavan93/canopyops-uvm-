"""enable row-level security (DB-enforced tenant isolation)

Creates a non-superuser app role (superusers bypass RLS) and RLS policies keyed
on the transaction GUC ``app.tenant_id`` (set per request by the app). The
program-owned tables refuse cross-program rows at the database, not just the app
layer. ``job`` is intentionally excluded — the worker claims jobs across all
programs (it's scoped in application code + when it runs each job's handler).

The role and password are DERIVED FROM ``DATABASE_URL`` rather than written here.
They used to be two module constants, which made this file a second declaration
of a fact ``DATABASE_URL`` already states — so the two could disagree, and the
password was a copy of the username. Neon's control plane rejects that outright
(*"insecure password"*) at COMMIT, after every migration appears to run, rolling
the whole schema back. Deriving means there is one place to change a credential
and no way for the app to hold a password the role was never given.

Revision ID: f7a1c2d8e934
Revises: e5c3d9a71b42
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.engine import make_url

from app.core.config import get_settings

revision: str = "f7a1c2d8e934"
down_revision: Union[str, None] = "e5c3d9a71b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _app_credentials() -> tuple[str, str]:
    """Who the app connects as, per DATABASE_URL — the only declaration of it.

    make_url percent-decodes, so a password containing @ / : / % survives being
    embedded in a URL and is compared/created in its real form.
    """
    url = make_url(get_settings().database_url)
    if not url.username or not url.password:
        raise RuntimeError(
            "DATABASE_URL must carry the app role's username and password: this "
            "migration creates that role from them. Got a URL with "
            f"username={url.username!r}, password={'set' if url.password else 'missing'}."
        )
    return url.username, url.password

# Program-owned tables that get RLS (job is excluded — see module docstring).
_RLS_TABLES = [
    "corridor", "work_order", "treatment_plan", "treatment_execution",
    "evidence_item", "verification_observation", "sync_attempt",
    "risk_review", "quality_audit", "audit_event",
]


def upgrade() -> None:
    bind = op.get_bind()
    role, password = _app_credentials()

    # quote_ident/quote_literal are Postgres' own quoting — correct for any
    # identifier or password, including ones with quotes or backslashes in them.
    ident, secret = bind.exec_driver_sql(
        "SELECT quote_ident(%s), quote_literal(%s)", (role, password)
    ).one()

    # 1) A non-superuser role the API/worker connect as (so RLS applies).
    #
    # Skipped when the app already connects as the role running this migration
    # (single-role dev, where ADMIN_DATABASE_URL is unset and both URLs are the
    # owner). Creating it would be a no-op, but ALTERing it NOSUPERUSER would
    # strip privileges from the very connection executing this statement.
    # RLS is then not enforced for that role — the tradeoff config.py documents.
    if role != bind.exec_driver_sql("SELECT current_user").scalar():
        exists = bind.exec_driver_sql(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
        ).first()
        # ALTER rather than skip when it exists, so rotating the password in
        # DATABASE_URL and redeploying is sufficient to rotate it for real.
        verb = "ALTER" if exists else "CREATE"
        bind.exec_driver_sql(
            f"{verb} ROLE {ident} WITH LOGIN PASSWORD {secret} "
            "NOSUPERUSER NOCREATEDB NOCREATEROLE"
        )

    # 2) Grants: CRUD on current + future tables, read PostGIS' SRS table.
    op.execute(f"GRANT USAGE ON SCHEMA public TO {ident}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {ident}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {ident}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {ident}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {ident}")

    # 3) RLS: policies read the transaction GUC app.tenant_id. Unset GUC ->
    #    current_setting returns NULL -> no rows match (fail closed).
    for t in _RLS_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {t}
              USING (tenant_id = current_setting('app.tenant_id', true))
              WITH CHECK (tenant_id = current_setting('app.tenant_id', true))
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    role, _ = _app_credentials()
    ident = bind.exec_driver_sql("SELECT quote_ident(%s)", (role,)).scalar()

    for t in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {ident}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {ident}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {ident}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {ident}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {ident}")

    # Never drop the role we are connected as (single-role dev — see upgrade).
    if role != bind.exec_driver_sql("SELECT current_user").scalar():
        op.execute(f"DROP ROLE IF EXISTS {ident}")
