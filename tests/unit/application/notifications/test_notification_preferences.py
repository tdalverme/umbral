"""Notification preferences model and unsubscribe token tests (H5)."""

from __future__ import annotations

from datetime import datetime, time, timezone
from uuid import uuid4

import pytest

from umbral.application.notifications.contracts import (
    NotificationPreferences,
    PlannerValidationError,
)
from umbral.application.notifications.preferences import (
    bump_version,
    make_unsubscribe_token,
    validate_preferences,
    verify_unsubscribe_token,
)

_SECRET = b"test-secret"


def test_validate_preferences_accepts_defaults() -> None:
    validate_preferences(NotificationPreferences())


def test_validate_preferences_rejects_invalid_timezone() -> None:
    with pytest.raises(PlannerValidationError):
        validate_preferences(NotificationPreferences(timezone="Not/AZone"))


def test_validate_preferences_rejects_bad_digest_hour() -> None:
    with pytest.raises(PlannerValidationError):
        validate_preferences(NotificationPreferences(digest_local_hour=24))


def test_validate_preferences_rejects_bad_threshold() -> None:
    with pytest.raises(PlannerValidationError):
        validate_preferences(NotificationPreferences(score_threshold=1.2))


def test_bump_version_increments() -> None:
    bumped = bump_version(NotificationPreferences())
    assert bumped.version == 2


def test_unsubscribe_token_roundtrip() -> None:
    user_id = uuid4()
    search_id = uuid4()
    now = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)
    token = make_unsubscribe_token(
        secret=_SECRET,
        user_id=user_id,
        search_profile_id=search_id,
        version=1,
        ttl_hours=24,
        now=now,
    )
    assert verify_unsubscribe_token(
        secret=_SECRET,
        token=token,
        user_id=user_id,
        search_profile_id=search_id,
        version=1,
        now=now,
    ) is True


def test_unsubscribe_token_rejects_wrong_user() -> None:
    user_id = uuid4()
    now = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)
    token = make_unsubscribe_token(
        secret=_SECRET,
        user_id=user_id,
        search_profile_id=uuid4(),
        version=1,
        ttl_hours=24,
        now=now,
    )
    assert verify_unsubscribe_token(
        secret=_SECRET,
        token=token,
        user_id=uuid4(),
        search_profile_id=uuid4(),
        version=1,
        now=now,
    ) is False


def test_unsubscribe_token_expires() -> None:
    user_id = uuid4()
    search_id = uuid4()
    now = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)
    token = make_unsubscribe_token(
        secret=_SECRET,
        user_id=user_id,
        search_profile_id=search_id,
        version=1,
        ttl_hours=24,
        now=now,
    )
    later = datetime(2026, 8, 13, 15, 0, tzinfo=timezone.utc)
    assert verify_unsubscribe_token(
        secret=_SECRET,
        token=token,
        user_id=user_id,
        search_profile_id=search_id,
        version=1,
        now=later,
    ) is False


def test_unsubscribe_token_invalidated_by_version_change() -> None:
    user_id = uuid4()
    search_id = uuid4()
    now = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)
    token = make_unsubscribe_token(
        secret=_SECRET,
        user_id=user_id,
        search_profile_id=search_id,
        version=1,
        ttl_hours=24,
        now=now,
    )
    assert verify_unsubscribe_token(
        secret=_SECRET,
        token=token,
        user_id=user_id,
        search_profile_id=search_id,
        version=2,
        now=now,
    ) is False


def test_quiet_hours_time_defaults() -> None:
    prefs = NotificationPreferences()
    assert prefs.quiet_hours_start == time(22, 0)
    assert prefs.quiet_hours_end == time(8, 0)
