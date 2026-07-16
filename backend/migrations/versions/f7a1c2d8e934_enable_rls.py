"""enable row-level security (DB-enforced tenant isolation)

Creates a non-superuser app role (superusers bypass RLS) and RLS policies keyed
on the transaction GUC ``app.tenant_id`` (set per request by the app). The
program-owned tables refuse cross-program rows at the database, not just the app
layer. ``job`` is intentionally excluded — the worker claims jobs across all
programs (it's scoped in application code + when it runs each job's handler).

Revision ID: f7a1c2d8e934
Revises: e5c3d9a71b42
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f7a1c2d8e934"
down_revision: Union[str, None] = "e5c3d9a71b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

APP_ROLE = "canopyops_app"
APP_PASSWORD = "canopyops_app"  # synthetic demo credential

# Program-owned tables that get RLS (job is excluded — see module docstring).
_RLS_TABLES = [
    "corridor", "work_order", "treatment_plan", "treatment_execution",
    "evidence_item", "verification_observation", "sync_attempt",
    "risk_review", "quality_audit", "audit_event",
]


def upgrade() -> None:
    # 1) A non-superuser role the API/worker connect as (so RLS applies).
    op.execute(
        f"""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
            CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
          END IF;
        END
        $$;
        """
    )
    # 2) Grants: CRUD on current + future tables, read PostGIS' SRS table.
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}")

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
    for t in _RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {APP_ROLE}")
    op.execute(f"REVOKE USAGE ON SCHEMA public FROM {APP_ROLE}")
    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE}")
