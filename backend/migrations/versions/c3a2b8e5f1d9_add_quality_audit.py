"""add quality_audit (independent QA audit of completed work plans)

Revision ID: c3a2b8e5f1d9
Revises: b2f1a9c4d7e0
Create Date: 2026-07-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3a2b8e5f1d9"
down_revision: Union[str, None] = "b2f1a9c4d7e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quality_audit",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("plan_id", sa.String(), nullable=False),
        sa.Column("auditor_id", sa.String(), nullable=True),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["plan_id"], ["treatment_plan.id"]),
        sa.ForeignKeyConstraint(["auditor_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quality_audit_plan_id", "quality_audit", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_quality_audit_plan_id", table_name="quality_audit")
    op.drop_table("quality_audit")
