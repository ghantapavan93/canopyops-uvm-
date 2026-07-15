"""add risk_review (persisted human sign-off on span risk)

Revision ID: b2f1a9c4d7e0
Revises: 076f6ab98187
Create Date: 2026-07-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2f1a9c4d7e0"
down_revision: Union[str, None] = "076f6ab98187"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "risk_review",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("plan_id", sa.String(), nullable=False),
        sa.Column("reviewer_id", sa.String(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False, server_default="acknowledged"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["plan_id"], ["treatment_plan.id"]),
        sa.ForeignKeyConstraint(["reviewer_id"], ["app_user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_risk_review_plan_id", "risk_review", ["plan_id"])


def downgrade() -> None:
    op.drop_index("ix_risk_review_plan_id", table_name="risk_review")
    op.drop_table("risk_review")
