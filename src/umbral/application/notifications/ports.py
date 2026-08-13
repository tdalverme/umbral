"""Ports for proactive notifications; infrastructure supplies adapters (H5)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from umbral.application.notifications.contracts import (
    NotificationPreferences,
)


class PreferenceRepository(Protocol):
    """Versioned notification preferences for one user/search."""

    def get(
        self, *, user_id: UUID, search_profile_id: UUID
    ) -> NotificationPreferences | None: ...

    def upsert(
        self,
        *,
        user_id: UUID,
        search_profile_id: UUID,
        preferences: NotificationPreferences,
        now: datetime,
        correlation_id: UUID,
    ) -> NotificationPreferences: ...


class DecisionRepository(Protocol):
    """Persisted planner decisions with dedupe."""

    def insert(
        self,
        *,
        user_id: UUID,
        search_profile_id: UUID,
        recommendation_item_id: UUID,
        trigger: str,
        reason_code: str,
        decision_state: str,
        policy_version: str,
        preferences_version: int,
        price_before: float | None,
        price_after: float | None,
        duplicate_of_id: UUID | None,
        now: datetime,
        correlation_id: UUID,
    ) -> UUID: ...

    def get(self, decision_id: UUID) -> Mapping[str, object] | None: ...

    def find_by_item_trigger(
        self, *, recommendation_item_id: UUID, trigger: str
    ) -> UUID | None: ...

    def list_recent(
        self, *, user_id: UUID, search_profile_id: UUID, since: datetime
    ) -> Sequence[Mapping[str, object]]: ...

    def pending_digest(
        self, *, search_profile_id: UUID
    ) -> Sequence[Mapping[str, object]]: ...

    def mark_delivered(
        self, *, decision_id: UUID, provider_message_id: str, now: datetime
    ) -> bool: ...


class ProfileNotificationReader(Protocol):
    """Reads active profiles and their latest published recommendation items."""

    def list_active_profiles(self) -> Sequence[Mapping[str, object]]: ...

    def latest_candidates(
        self, *, search_profile_id: UUID
    ) -> Sequence[Mapping[str, object]]: ...


class UserEmailReader(Protocol):
    """Reads the normalized email of a product user for delivery."""

    def email_for(self, user_id: UUID) -> str | None: ...


class InboxRepository(Protocol):
    """Web inbox items 1:1 with decisions."""

    def add_for_decision(
        self, *, decision_id: UUID, user_id: UUID, now: datetime
    ) -> None: ...

    def list_for_user(
        self, *, user_id: UUID, limit: int, after: object | None
    ) -> Sequence[Mapping[str, object]]: ...

    def mark_read(self, *, user_id: UUID, decision_id: UUID, now: datetime) -> bool: ...


class NotificationEmailPort(Protocol):
    """Transactional email delivery for notification decisions."""

    provider: str

    def send_decision_email(
        self,
        *,
        to_email: str,
        subject: str,
        body_html: str,
        decision_id: UUID,
        provider_message_id: str,
        now: datetime,
        correlation_id: UUID | None = None,
    ) -> str: ...
