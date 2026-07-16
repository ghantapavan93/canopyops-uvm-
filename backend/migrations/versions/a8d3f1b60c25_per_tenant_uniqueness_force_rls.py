"""per-program uniqueness (work_order.reference, sync_attempt idempotency) + FORCE RLS

Fixes a multi-tenant collision: work_order.reference was globally unique but the
generator counts a program's own work orders, so two programs could collide.
Makes it (and the sync idempotency key) unique PER PROGRAM. Also adds FORCE ROW
LEVEL SECURITY so the policies apply even to the table owner.

Revision ID: a8d3f1b60c25
Revises: f7a1c2d8e934
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a8d3f1b60c25"
down_revision: Union[str, None] = "f7a1c2d8e934"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_TABLES = [
    "corridor", "work_order", "treatment_plan", "treatment_execution",
    "evidence_item", "verification_observation", "sync_attempt",
    "risk_review", "quality_audit", "audit_event",
]


def upgrade() -> None:
    # work_order.reference: global unique index -> non-unique index + per-program unique
    op.drop_index("ix_work_order_reference", table_name="work_order")
    op.create_index("ix_work_order_reference", "work_order", ["reference"])
    op.create_unique_constraint(
        "uq_work_order_ref_per_tenant", "work_order", ["tenant_id", "reference"]
    )

    # sync_attempt idempotency: add tenant to the uniqueness
    op.drop_constraint("uq_idempotency", "sync_attempt", type_="unique")
    op.create_unique_constraint(
        "uq_idempotency", "sync_attempt", ["tenant_id", "entity_type", "idempotency_key"]
    )

    # FORCE RLS so a table owner (not just a plain role) is also subject to it.
    for t in _RLS_TABLES:
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    for t in _RLS_TABLES:
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
    op.drop_constraint("uq_idempotency", "sync_attempt", type_="unique")
    op.create_unique_constraint("uq_idempotency", "sync_attempt", ["entity_type", "idempotency_key"])
    op.drop_constraint("uq_work_order_ref_per_tenant", "work_order", type_="unique")
    op.drop_index("ix_work_order_reference", table_name="work_order")
    op.create_index("ix_work_order_reference", "work_order", ["reference"], unique=True)
