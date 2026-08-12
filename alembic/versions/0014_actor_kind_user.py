"""Extend actor_kind with 'user' (chat and feedback actors).

The shared ``actor_kind`` enum only accepted ``system``/``service``/``operator``
while the chat and feedback flows record ``user`` as the actor; inserts into
any audited table from those flows failed with a DB enum error. This migration
adds the value (Postgres >= 12 allows ALTER TYPE ADD VALUE inside a
transaction).
"""

from __future__ import annotations

from alembic import op

revision = "0014_actor_kind_user"
down_revision = "0013_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE actor_kind ADD VALUE IF NOT EXISTS 'user'")


def downgrade() -> None:
    # Postgres cannot remove enum values; the downgrade is a no-op with a
    # documented note (the value remains unused once no rows reference it).
    pass
