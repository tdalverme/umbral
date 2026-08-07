"""Scoring v1: policies, evaluations, explanations data and comparison shortlists."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base, IdentityAuditMixin

EVALUATION_STATE = ENUM(
    "match", "mismatch", "unknown", name="evaluation_state", create_type=True
)


class ScoringPolicy(IdentityAuditMixin, Base):
    __tablename__ = "scoring_policies"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint("policy_key", name="uq_scoring_policies_key"),
        CheckConstraint(
            "policy_key ~ '^[a-z][a-z0-9_-]{1,99}$'",
            name="ck_scoring_policies_key",
        ),
        Index("ix_scoring_policies_created", "created_at"),
    )

    policy_key: Mapped[str] = mapped_column(String(100), nullable=False)
    current_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


class ScoringPolicyVersion(IdentityAuditMixin, Base):
    __tablename__ = "scoring_policy_versions"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "policy_id",
            "policy_version",
            name="uq_scoring_policy_versions_policy_version",
        ),
        CheckConstraint(
            "policy_version >= 1", name="ck_scoring_policy_versions_policy_version"
        ),
        Index("ix_scoring_policy_versions_policy", "policy_id", "created_at"),
    )

    policy_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("scoring_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_version: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class CriterionEvaluation(IdentityAuditMixin, Base):
    __tablename__ = "criterion_evaluations"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "listing_id",
            "criterion_key",
            name="uq_criterion_evaluations_run_listing_criterion",
        ),
        CheckConstraint(
            "score >= 0 AND score <= 1", name="ck_criterion_evaluations_score"
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_criterion_evaluations_confidence",
        ),
        Index("ix_criterion_evaluations_run_listing", "run_id", "listing_id"),
        Index("ix_criterion_evaluations_run_criterion", "run_id", "criterion_key"),
        Index("ix_criterion_evaluations_listing", "listing_id"),
    )

    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("recommendation_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    listing_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("silver_listings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    criterion_key: Mapped[str] = mapped_column(String(120), nullable=False)
    criterion_version: Mapped[str] = mapped_column(String(100), nullable=False)
    matcher_type: Mapped[str] = mapped_column(String(50), nullable=False)
    params: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    input_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    score: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    state: Mapped[str] = mapped_column(EVALUATION_STATE, nullable=False)
    contribution: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    evidence_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )


class ComparisonShortlist(IdentityAuditMixin, Base):
    __tablename__ = "comparison_shortlists"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "profile_id", "listing_id", name="uq_comparison_shortlists_profile_listing"
        ),
        UniqueConstraint(
            "profile_id", "position", name="uq_comparison_shortlists_profile_position"
        ),
        CheckConstraint("position >= 0", name="ck_comparison_shortlists_position"),
        Index("ix_comparison_shortlists_profile", "profile_id"),
    )

    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    listing_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("silver_listings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
