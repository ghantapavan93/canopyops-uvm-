"""add tenant isolation (per-program row scoping)

Revision ID: e5c3d9a71b42
Revises: d4b7c1f9a2e3
Create Date: 2026-07-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5c3d9a71b42"
down_revision: Union[str, None] = "d4b7c1f9a2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Program-owned tables (auto-scoped) + app_user (carries membership).
_SCOPED = [
    "corridor", "work_order", "treatment_plan", "treatment_execution",
    "evidence_item", "verification_observation", "sync_attempt",
    "risk_review", "quality_audit", "job", "audit_event",
]
_ALL = _SCOPED + ["app_user"]


def upgrade() -> None:
    op.create_table(
        "tenant",
        sa.Column("id", sa.String(), nullable=False),         # slug
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    # Seed the default program so existing rows can be backfilled (seed replaces
    # these on the next run).
    op.execute("INSERT INTO tenant (id, name) VALUES ('demo', 'CanopyOps Demo Utility') ON CONFLICT DO NOTHING")
    op.execute("INSERT INTO tenant (id, name) VALUES ('northgrid', 'NorthGrid Power (isolation demo)') ON CONFLICT DO NOTHING")

    for t in _ALL:
        op.add_column(t, sa.Column("tenant_id", sa.String(), nullable=True))
        op.execute(f"UPDATE {t} SET tenant_id = 'demo' WHERE tenant_id IS NULL")
        op.alter_column(t, "tenant_id", nullable=False)
        op.create_index(f"ix_{t}_tenant_id", t, ["tenant_id"])
        op.create_foreign_key(f"fk_{t}_tenant", t, "tenant", ["tenant_id"], ["id"])


def downgrade() -> None:
    for t in _ALL:
        op.drop_constraint(f"fk_{t}_tenant", t, type_="foreignkey")
        op.drop_index(f"ix_{t}_tenant_id", table_name=t)
        op.drop_column(t, "tenant_id")
    op.drop_table("tenant")
