"""Add 'urban' to the observation source enum (fase 3).

Urban signals are consolidated into observations with ``source = urban``
through the same channel the scoring consumes; the enum needs the new value
(Postgres >= 12 allows ALTER TYPE ADD VALUE inside a transaction).
"""

from __future__ import annotations

from alembic import op

revision = "0015_observation_source_urban"
down_revision = "0014_actor_kind_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE observation_source ADD VALUE IF NOT EXISTS 'urban'")


def downgrade() -> None:
    # Postgres cannot remove enum values; the downgrade is a no-op with a
    # documented note (the value remains unused once no rows reference it).
    pass
