"""Scoring and explanations schema: policies, evaluations, comparison shortlists."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_scoring_explanations"
down_revision = "0006_criteria_observations"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _enum(name: str) -> postgresql.ENUM:
    values = {
        "actor_kind": ("system", "service", "operator"),
        "evaluation_state": ("match", "mismatch", "unknown"),
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
    op.execute("CREATE TYPE evaluation_state AS ENUM ('match', 'mismatch', 'unknown')")


def _drop_types() -> None:
    op.execute("DROP TYPE IF EXISTS evaluation_state")


def upgrade() -> None:
    _create_types()

    op.create_table(
        "scoring_policies",
        *_audit_columns(),
        sa.Column("policy_key", sa.String(100), nullable=False),
        sa.Column("current_version_id", _uuid()),
        sa.UniqueConstraint("policy_key", name="uq_scoring_policies_key"),
        sa.CheckConstraint(
            "policy_key ~ '^[a-z][a-z0-9_-]{1,99}$'", name="ck_scoring_policies_key"
        ),
        sa.Index("ix_scoring_policies_created", "created_at"),
    )
    op.create_table(
        "scoring_policy_versions",
        *_audit_columns(),
        sa.Column(
            "policy_id",
            _uuid(),
            sa.ForeignKey("scoring_policies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("contract_version", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "policy_id",
            "policy_version",
            name="uq_scoring_policy_versions_policy_version",
        ),
        sa.CheckConstraint(
            "policy_version >= 1", name="ck_scoring_policy_versions_policy_version"
        ),
        sa.Index("ix_scoring_policy_versions_policy", "policy_id", "created_at"),
    )
    op.create_table(
        "criterion_evaluations",
        *_audit_columns(),
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
        sa.Column("criterion_key", sa.String(120), nullable=False),
        sa.Column("criterion_version", sa.String(100), nullable=False),
        sa.Column("matcher_type", sa.String(50), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("input_refs", postgresql.JSONB(), nullable=False),
        sa.Column("score", sa.Numeric(6, 4), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("state", _enum("evaluation_state"), nullable=False),
        sa.Column("contribution", sa.Numeric(6, 4), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "score >= 0 AND score <= 1", name="ck_criterion_evaluations_score"
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_criterion_evaluations_confidence",
        ),
        sa.UniqueConstraint(
            "run_id",
            "listing_id",
            "criterion_key",
            name="uq_criterion_evaluations_run_listing_criterion",
        ),
        sa.Index("ix_criterion_evaluations_run_listing", "run_id", "listing_id"),
        sa.Index("ix_criterion_evaluations_run_criterion", "run_id", "criterion_key"),
        sa.Index("ix_criterion_evaluations_listing", "listing_id"),
    )
    op.create_table(
        "comparison_shortlists",
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
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint(
            "profile_id",
            "listing_id",
            name="uq_comparison_shortlists_profile_listing",
        ),
        sa.UniqueConstraint(
            "profile_id",
            "position",
            name="uq_comparison_shortlists_profile_position",
        ),
        sa.CheckConstraint("position >= 0", name="ck_comparison_shortlists_position"),
        sa.Index("ix_comparison_shortlists_profile", "profile_id"),
    )


def downgrade() -> None:
    for name in (
        "comparison_shortlists",
        "criterion_evaluations",
        "scoring_policy_versions",
        "scoring_policies",
    ):
        op.drop_table(name)
    _drop_types()
