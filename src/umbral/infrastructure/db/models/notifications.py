"""Notification preferences, decisions and inbox ORM models (H5)."""

from __future__ import annotations

from datetime import datetime, time
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base, IdentityAuditMixin

NOTIFICATION_TRIGGER = ENUM(
    "new_match", "price_drop", name="notification_trigger", create_type=True
)
NOTIFICATION_DECISION_STATE = ENUM(
    "pending_delivery",
    "pending_digest",
    "postponed",
    "duplicated",
    "discarded",
    "delivered",
    "read",
    "acted",
    name="notification_decision_state",
    create_type=True,
)
NOTIFICATION_PREF_STATE = ENUM(
    "active", "paused", "disabled", name="notification_pref_state", create_type=True
)


class NotificationPreferencesModel(IdentityAuditMixin, Base):
    """Versioned per-user/per-search notification preferences."""

    __tablename__ = "notification_preferences"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_users.id"),
        nullable=False,
    )
    search_profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("search_profiles.id"),
        nullable=False,
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    inbox_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    quiet_hours_start: Mapped[time] = mapped_column(Time, nullable=False)
    quiet_hours_end: Mapped[time] = mapped_column(Time, nullable=False)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    digest_local_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    score_threshold: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    state: Mapped[str] = mapped_column(NOTIFICATION_PREF_STATE, nullable=False)
    __table_args__ = (
        Index("ix_notification_prefs_user", "user_id"),
        Index("ix_notification_prefs_search", "search_profile_id"),
    )


class NotificationDecisionModel(IdentityAuditMixin, Base):
    """One deterministic planner decision, deduplicated by item+trigger."""

    __tablename__ = "notification_decisions"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        Index("ix_notification_decisions_user_created", "user_id", "created_at"),
        Index("ix_notification_decisions_state_digest", "decision_state"),
        Index(
            "uq_notification_decision_item_trigger",
            "recommendation_item_id",
            "trigger",
            unique=True,
            postgresql_where=text(
                "decision_state IN "
                "('pending_delivery', 'pending_digest', 'postponed', "
                "'delivered', 'read', 'acted')"
            ),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("product_users.id"), nullable=False
    )
    search_profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("search_profiles.id"), nullable=False
    )
    recommendation_item_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recommendation_items.id"), nullable=False
    )
    trigger: Mapped[str] = mapped_column(NOTIFICATION_TRIGGER, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    reason_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    preferences_version: Mapped[int] = mapped_column(Integer, nullable=False)
    price_before: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    price_after: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    decision_state: Mapped[str] = mapped_column(
        NOTIFICATION_DECISION_STATE, nullable=False
    )
    duplicate_of_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)


class NotificationInboxItemModel(IdentityAuditMixin, Base):
    """Web inbox view of a decision (1:1, same source of truth as email)."""

    __tablename__ = "notification_inbox_items"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint("decision_id"),
        Index("ix_notification_inbox_user_created", "user_id", "created_at"),
    )

    decision_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("notification_decisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("product_users.id"), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
