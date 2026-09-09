"""Cache grounded opportunity narratives by frozen run and generation version."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0025_recommendation_narratives"
down_revision = "0024_conversation_v5_proposal_total"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _actor_kind() -> postgresql.ENUM:
    return postgresql.ENUM(
        "system", "service", "operator", name="actor_kind", create_type=False
    )


def upgrade() -> None:
    op.create_table(
        "recommendation_narratives",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", _ts(), nullable=False),
        sa.Column("updated_at", _ts(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("actor_kind", _actor_kind(), nullable=False, server_default="system"),
        sa.Column("actor_id", sa.String(128)),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
        sa.Column(
            "run_id",
            _uuid(),
            sa.ForeignKey("recommendation_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "listing_id",
            _uuid(),
            sa.ForeignKey("silver_listings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.String(100), nullable=False),
        sa.Column("text", sa.String(900), nullable=False),
        sa.Column("used_criteria", postgresql.JSONB(), nullable=False),
        sa.Column("used_evidence_refs", postgresql.JSONB(), nullable=False),
        sa.Column("narrative_source", sa.String(32), nullable=False),
        sa.Column("output_model_version", sa.String(100), nullable=False),
        sa.UniqueConstraint(
            "run_id",
            "listing_id",
            "prompt_version",
            "model_version",
            "schema_version",
            name="uq_recommendation_narratives_cache_key",
        ),
        sa.CheckConstraint(
            "char_length(text) > 0 AND char_length(text) <= 900",
            name="ck_recommendation_narratives_text",
        ),
        sa.CheckConstraint(
            "narrative_source IN ('managed', 'deterministic_fallback')",
            name="ck_recommendation_narratives_source",
        ),
        sa.Index("ix_recommendation_narratives_run_listing", "run_id", "listing_id"),
    )


def downgrade() -> None:
    op.drop_table("recommendation_narratives")
