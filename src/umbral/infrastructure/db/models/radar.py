"""Structured search radar: profiles, versions, runs, items and product events."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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

SEARCH_PROFILE_STATE = ENUM(
    "active", "paused", "archived", name="search_profile_state", create_type=True
)
RECOMMENDATION_RUN_STATE = ENUM(
    "pending",
    "running",
    "succeeded",
    "failed",
    name="recommendation_run_state",
    create_type=True,
)
RECOMMENDATION_RUN_TRIGGER = ENUM(
    "created", "edited", "resumed", name="recommendation_run_trigger", create_type=True
)


class SearchProfile(IdentityAuditMixin, Base):
    __tablename__ = "search_profiles"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_search_profiles_owner_name"),
        CheckConstraint(
            "budget_max > 0 AND (budget_min IS NULL OR budget_min < budget_max)",
            name="ck_search_profiles_budget",
        ),
        CheckConstraint(
            "surface_min >= 0 AND (surface_max IS NULL OR surface_max > surface_min)",
            name="ck_search_profiles_surface",
        ),
        CheckConstraint(
            "min_rooms >= 0 AND min_rooms <= 200",
            name="ck_search_profiles_rooms",
        ),
        Index("ix_search_profiles_owner_status", "owner_id", "status"),
        Index("ix_search_profiles_owner_created", "owner_id", "created_at"),
    )

    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    zones: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    budget_max: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    budget_min: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    min_rooms: Mapped[int] = mapped_column(Integer, nullable=False)
    surface_min: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    surface_max: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(SEARCH_PROFILE_STATE, nullable=False)
    unknown_strategy: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    current_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    latest_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


class SearchProfileVersion(IdentityAuditMixin, Base):
    __tablename__ = "search_profile_versions"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "profile_version",
            name="uq_search_profile_versions_profile_version",
        ),
        CheckConstraint(
            "profile_version >= 1",
            name="ck_search_profile_versions_profile_version",
        ),
    )

    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class RecommendationRun(IdentityAuditMixin, Base):
    __tablename__ = "recommendation_runs"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "profile_version_id",
            "trigger",
            name="uq_recommendation_runs_profile_version",
        ),
        CheckConstraint(
            "state IN ('pending', 'running', 'succeeded', 'failed')"
            " AND (state IN ('pending', 'running') OR finished_at IS NOT NULL)",
            name="ck_recommendation_runs_state_finished",
        ),
        Index("ix_recommendation_runs_profile_state", "profile_id", "state"),
        Index("ix_recommendation_runs_profile_created", "profile_id", "created_at"),
        Index("ix_recommendation_runs_profile_version", "profile_version_id"),
    )

    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    profile_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("search_profile_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(RECOMMENDATION_RUN_STATE, nullable=False)
    trigger: Mapped[str] = mapped_column(RECOMMENDATION_RUN_TRIGGER, nullable=False)
    score_policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_item_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    job_execution_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RecommendationItem(IdentityAuditMixin, Base):
    __tablename__ = "recommendation_items"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "run_id", "position", name="uq_recommendation_items_run_position"
        ),
        UniqueConstraint(
            "run_id", "listing_id", name="uq_recommendation_items_run_listing"
        ),
        CheckConstraint(
            "score >= 0 AND score <= 1", name="ck_recommendation_items_score"
        ),
        CheckConstraint("position >= 0", name="ck_recommendation_items_position"),
        Index("ix_recommendation_items_run_position", "run_id", "position"),
        Index("ix_recommendation_items_listing", "listing_id"),
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
    score: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    contributions: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )


class ProductEventRow(IdentityAuditMixin, Base):
    __tablename__ = "product_events"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        CheckConstraint(
            "event_type ~ '^[a-z][a-z0-9_.]{0,99}$'",
            name="ck_product_events_type",
        ),
        Index("ix_product_events_type_occurred", "event_type", "occurred_at"),
        Index("ix_product_events_occurred", "occurred_at"),
        Index("ix_product_events_actor", "actor_id"),
    )

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
