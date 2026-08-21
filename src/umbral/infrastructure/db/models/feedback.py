"""Feedback and learning: immutable feedback events, quick reasons, learning policies and proposals."""
# ruff: noqa: E501

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base, IdentityAuditMixin

FEEDBACK_EVENT_TYPE = ENUM(
    "like", "dislike", "save", "dismiss", "contacted",
    name="feedback_event_type",
    create_type=True,
)
FEEDBACK_EVENT_STATE = ENUM(
    "active", "superseded",
    name="feedback_event_state",
    create_type=True,
)
FEEDBACK_POLARITY = ENUM(
    "positive", "negative", "neutral",
    name="feedback_polarity",
    create_type=True,
)
FEEDBACK_STRENGTH = ENUM(
    "low", "medium", "strong",
    name="feedback_strength",
    create_type=True,
)
LEARNING_PROPOSAL_STATE = ENUM(
    "pending", "confirmed", "rejected", "expired", "superseded",
    name="learning_proposal_state",
    create_type=True,
)


class FeedbackEvent(IdentityAuditMixin, Base):
    __tablename__ = "feedback_events"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "idempotency_key",
            name="uq_feedback_events_profile_idempotency",
        ),
        Index(
            "uq_feedback_events_active",
            "profile_id",
            "listing_id",
            unique=True,
            postgresql_where=text("state = 'active'"),
        ),
        CheckConstraint(
            "idempotency_key <> ''", name="ck_feedback_events_idempotency_key"
        ),
        Index("ix_feedback_events_profile_listing", "profile_id", "listing_id", "created_at"),
        Index("ix_feedback_events_profile_state", "profile_id", "state"),
        Index("ix_feedback_events_listing", "listing_id"),
        Index("ix_feedback_events_superseded_by", "superseded_by"),
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
    run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("recommendation_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(FEEDBACK_EVENT_TYPE, nullable=False)
    state: Mapped[str] = mapped_column(FEEDBACK_EVENT_STATE, nullable=False)
    superseded_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "feedback_events.id",
            ondelete="SET NULL",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    free_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)


class FeedbackEventReason(IdentityAuditMixin, Base):
    __tablename__ = "feedback_event_reasons"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "event_id", "reason_key", name="uq_feedback_event_reasons_event_key"
        ),
        Index("ix_feedback_event_reasons_event", "event_id"),
        Index("ix_feedback_event_reasons_concept", "concept_id"),
    )

    event_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("feedback_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason_key: Mapped[str] = mapped_column(String(100), nullable=False)
    concept_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("concepts.id", ondelete="RESTRICT"),
        nullable=True,
    )
    polarity: Mapped[str] = mapped_column(FEEDBACK_POLARITY, nullable=False)
    strength: Mapped[str | None] = mapped_column(
        FEEDBACK_STRENGTH, nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)


class LearningPolicy(IdentityAuditMixin, Base):
    __tablename__ = "learning_policies"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint("policy_key", name="uq_learning_policies_key"),
        CheckConstraint(
            "policy_key ~ '^[a-z][a-z0-9_-]{1,99}$'",
            name="ck_learning_policies_key",
        ),
        Index("ix_learning_policies_created", "created_at"),
    )

    policy_key: Mapped[str] = mapped_column(String(100), nullable=False)
    current_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


class LearningPolicyVersion(IdentityAuditMixin, Base):
    __tablename__ = "learning_policy_versions"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "policy_id",
            "policy_version",
            name="uq_learning_policy_versions_policy_version",
        ),
        CheckConstraint(
            "policy_version >= 1", name="ck_learning_policy_versions_policy_version"
        ),
        Index("ix_learning_policy_versions_policy", "policy_id", "created_at"),
    )

    policy_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("learning_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_version: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class LearningProposal(IdentityAuditMixin, Base):
    __tablename__ = "learning_proposals"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        Index(
            "uq_learning_proposals_pending",
            "profile_id",
            "concept_id",
            unique=True,
            postgresql_where=text("state = 'pending'"),
        ),
        Index("ix_learning_proposals_profile_state", "profile_id", "state"),
        Index("ix_learning_proposals_profile_created", "profile_id", "created_at"),
        Index("ix_learning_proposals_concept", "concept_id"),
    )

    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    concept_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("concepts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    concept_key: Mapped[str] = mapped_column(String(120), nullable=False)
    policy_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("learning_policy_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    change: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    prior_fact: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True
    )
    evidence_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    state: Mapped[str] = mapped_column(LEARNING_PROPOSAL_STATE, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    superseded_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("learning_proposals.id", ondelete="SET NULL"),
        nullable=True,
    )
    applied_profile_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("search_profile_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    applied_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("recommendation_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
