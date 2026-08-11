"""Preferences service: read/update versioned notification preferences (H5)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from uuid import UUID

from umbral.application.notifications.contracts import NotificationPreferences
from umbral.application.notifications.ports import PreferenceRepository
from umbral.application.notifications.preferences import (
    validate_preferences,
)


class PreferencesService:
    """Ownership-scoped preferences with validation and version bump."""

    def __init__(
        self,
        *,
        repository: PreferenceRepository,
        default_timezone: str,
    ) -> None:
        self._repository = repository
        self._default_timezone = default_timezone

    def get(self, *, user_id: UUID, search_profile_id: UUID) -> NotificationPreferences:
        existing = self._repository.get(
            user_id=user_id, search_profile_id=search_profile_id
        )
        if existing is not None:
            return existing
        return NotificationPreferences(timezone=self._default_timezone)

    def update(
        self,
        *,
        user_id: UUID,
        search_profile_id: UUID,
        preferences: NotificationPreferences,
        now: datetime,
        correlation_id: UUID,
    ) -> NotificationPreferences:
        validate_preferences(preferences)
        current = self.get(user_id=user_id, search_profile_id=search_profile_id)
        updated = replace(
            preferences,
            timezone=preferences.timezone or current.timezone,
            version=current.version + 1,
        )
        validate_preferences(updated)
        return self._repository.upsert(
            user_id=user_id,
            search_profile_id=search_profile_id,
            preferences=updated,
            now=now,
            correlation_id=correlation_id,
        )
