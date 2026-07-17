"""enable postgis

Revision ID: a1e0d2c93b57
Revises:
Create Date: 2026-07-17 04:20:00.000000

WHY THIS MIGRATION EXISTS
-------------------------
The very next migration (076f6ab98187) creates Geometry columns, so the schema
has always depended on the postgis extension. Nothing in the chain created it.

It worked locally by accident of the environment: db/init/01-postgis.sql runs via
the postgres image's docker-entrypoint-initdb.d hook. That hook is a *Docker*
mechanism. It does not exist on Neon, RDS, Cloud SQL or any managed Postgres —
so the first real deploy failed with `type "geometry" does not exist`, and the
only thing standing between the repo and that failure was a human remembering
step 1 of a deploy doc.

A schema dependency belongs in the schema chain. `alembic upgrade head` against
an empty database is now sufficient on its own.

This runs under ADMIN_DATABASE_URL (the database owner), which is the role that
has rights to CREATE EXTENSION. The app role deliberately does not.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "a1e0d2c93b57"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS keeps this a no-op on databases where the extension is
    # already present — the compose stack (init hook) and any environment
    # stamped before this migration existed.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    # Deliberately not dropped. Every geometry column in the schema depends on
    # this type, so DROP EXTENSION would either fail or cascade into real data
    # loss. Downgrading past the initial schema removes those tables anyway; the
    # extension being left behind is harmless and IF NOT EXISTS makes re-upgrade
    # clean.
    pass
