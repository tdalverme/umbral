"""Feedback and learning schema: feedback events, quick reasons, learning policies, proposals."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_feedback_learning"
down_revision = "0007_scoring_explanations"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _enum(name: str) -> postgresql.ENUM:
    values = {
        "actor_kind": ("system", "service", "operator"),
        "feedback_event_type": ("like", "dislike", "save", "dismiss", "contacted"),
        "feedback_event_state": ("active", "superseded"),
        "feedback_polarity": ("positive", "negative", "neutral"),
        "learning_proposal_state": (
            "pending",
            "confirmed",
            "rejected",
            "expired",
            "superseded",
        ),
    }[name]
    return postgresql.ENUM(*values, name=name, create_type=False)


def _audit_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", _ts(), nullable=False),
        sa.Column("updated_at", _ts(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "actor_kind", _enum("actor_kind"), nullable=False, server_default="system"
        ),
        sa.Column("actor_id", sa.String(128)),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
    ]


def _create_types() -> None:
    op.execute(
        "CREATE TYPE feedback_event_type AS ENUM "
        "('like', 'dislike', 'save', 'dismiss', 'contacted')"
    )
    op.execute("CREATE TYPE feedback_event_state AS ENUM ('active', 'superseded')")
    op.execute(
        "CREATE TYPE feedback_polarity AS ENUM "
        "('positive', 'negative', 'neutral')"
    )
    op.execute(
        "CREATE TYPE learning_proposal_state AS ENUM "
        "('pending', 'confirmed', 'rejected', 'expired', 'superseded')"
    )


def _drop_types() -> None:
    op.execute("DROP TYPE IF EXISTS learning_proposal_state")
    op.execute("DROP TYPE IF EXISTS feedback_polarity")
    op.execute("DROP TYPE IF EXISTS feedback_event_state")
    op.execute("DROP TYPE IF EXISTS feedback_event_type")


def upgrade() -> None:
    _create_types()

    op.create_table(
        "feedback_events",
        *_audit_columns(),
        sa.Column(
            "profile_id",
            _uuid(),
            sa.ForeignKey("search_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "listing_id",
            _uuid(),
            sa.ForeignKey("silver_listings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            _uuid(),
            sa.ForeignKey("recommendation_runs.id", ondelete="RESTRICT"),
        ),
        sa.Column("event_type", _enum("feedback_event_type"), nullable=False),
        sa.Column("state", _enum("feedback_event_state"), nullable=False),
        sa.Column(
            "superseded_by",
            _uuid(),
            sa.ForeignKey(
                "feedback_events.id",
                ondelete="SET NULL",
                deferrable=True,
                initially="DEFERRED",
            ),
        ),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("free_feedback", sa.Text()),
        sa.UniqueConstraint(
            "profile_id",
            "idempotency_key",
            name="uq_feedback_events_profile_idempotency",
        ),
        sa.CheckConstraint(
            "idempotency_key <> ''", name="ck_feedback_events_idempotency_key"
        ),
        sa.Index("ix_feedback_events_profile_listing", "profile_id", "listing_id", "created_at"),
        sa.Index("ix_feedback_events_profile_state", "profile_id", "state"),
        sa.Index("ix_feedback_events_listing", "listing_id"),
        sa.Index("ix_feedback_events_superseded_by", "superseded_by"),
    )
    op.create_index(
        "uq_feedback_events_active",
        "feedback_events",
        ["profile_id", "listing_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )
    op.create_table(
        "feedback_event_reasons",
        *_audit_columns(),
        sa.Column(
            "event_id",
            _uuid(),
            sa.ForeignKey("feedback_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason_key", sa.String(100), nullable=False),
        sa.Column(
            "concept_id",
            _uuid(),
            sa.ForeignKey("concepts.id", ondelete="RESTRICT"),
        ),
        sa.Column("polarity", _enum("feedback_polarity"), nullable=False),
        sa.UniqueConstraint(
            "event_id", "reason_key", name="uq_feedback_event_reasons_event_key"
        ),
        sa.Index("ix_feedback_event_reasons_event", "event_id"),
        sa.Index("ix_feedback_event_reasons_concept", "concept_id"),
    )
    op.create_table(
        "learning_policies",
        *_audit_columns(),
        sa.Column("policy_key", sa.String(100), nullable=False),
        sa.Column("current_version_id", _uuid()),
        sa.UniqueConstraint("policy_key", name="uq_learning_policies_key"),
        sa.CheckConstraint(
            "policy_key ~ '^[a-z][a-z0-9_-]{1,99}$'", name="ck_learning_policies_key"
        ),
        sa.Index("ix_learning_policies_created", "created_at"),
    )
    op.create_table(
        "learning_policy_versions",
        *_audit_columns(),
        sa.Column(
            "policy_id",
            _uuid(),
            sa.ForeignKey("learning_policies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("contract_version", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "policy_id",
            "policy_version",
            name="uq_learning_policy_versions_policy_version",
        ),
        sa.CheckConstraint(
            "policy_version >= 1", name="ck_learning_policy_versions_policy_version"
        ),
        sa.Index("ix_learning_policy_versions_policy", "policy_id", "created_at"),
    )
    op.create_table(
        "learning_proposals",
        *_audit_columns(),
        sa.Column(
            "profile_id",
            _uuid(),
            sa.ForeignKey("search_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "concept_id",
            _uuid(),
            sa.ForeignKey("concepts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("concept_key", sa.String(120), nullable=False),
        sa.Column(
            "policy_version_id",
            _uuid(),
            sa.ForeignKey("learning_policy_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column("change", postgresql.JSONB(), nullable=False),
        sa.Column("prior_fact", postgresql.JSONB()),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False),
        sa.Column("state", _enum("learning_proposal_state"), nullable=False),
        sa.Column("expires_at", _ts(), nullable=False),
        sa.Column(
            "superseded_by",
            _uuid(),
            sa.ForeignKey("learning_proposals.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "applied_profile_version_id",
            _uuid(),
            sa.ForeignKey("search_profile_versions.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "applied_run_id",
            _uuid(),
            sa.ForeignKey("recommendation_runs.id", ondelete="SET NULL"),
        ),
        sa.Index("ix_learning_proposals_profile_state", "profile_id", "state"),
        sa.Index("ix_learning_proposals_profile_created", "profile_id", "created_at"),
        sa.Index("ix_learning_proposals_concept", "concept_id"),
    )
    op.create_index(
        "uq_learning_proposals_pending",
        "learning_proposals",
        ["profile_id", "concept_id"],
        unique=True,
        postgresql_where=sa.text("state = 'pending'"),
    )


def downgrade() -> None:
    for name in (
        "learning_proposals",
        "learning_policy_versions",
        "learning_policies",
        "feedback_event_reasons",
        "feedback_events",
    ):
        op.drop_table(name)
    _drop_types()
