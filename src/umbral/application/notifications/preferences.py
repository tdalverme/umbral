"""Pure notification preferences model and rules (H5, UM-H5-001/002).

Preference changes bump the version (a changed version invalidates
outstanding unsubscribe tokens). Validation is deterministic; zoneinfo and
quiet hours are checked here, never in the planner.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from umbral.application.notifications.contracts import (
    NotificationPreferences,
    PlannerValidationError,
)


def validate_preferences(preferences: NotificationPreferences) -> None:
    """Validate a preferences value; raises a typed error on violations."""
    try:
        ZoneInfo(preferences.timezone)
    except Exception as exc:  # noqa: BLE001 - zoneinfo raises multiple types
        raise PlannerValidationError(
            f"timezone_invalid:{preferences.timezone}"
        ) from exc
    if preferences.digest_local_hour < 0 or preferences.digest_local_hour > 23:
        raise PlannerValidationError("digest_hour_range")
    if not (0.0 <= preferences.score_threshold <= 1.0):
        raise PlannerValidationError("threshold_range")
    if preferences.state not in {"active", "paused", "disabled"}:
        raise PlannerValidationError("state_invalid")


def bump_version(preferences: NotificationPreferences) -> NotificationPreferences:
    """Return a copy with the version incremented."""
    from dataclasses import replace

    return replace(preferences, version=preferences.version + 1)


def _token_payload(
    *,
    user_id: UUID,
    search_profile_id: UUID,
    version: int,
    exp: int,
) -> str:
    return (
        f"{user_id}|{search_profile_id}|{version}|{exp}"
    )


def make_unsubscribe_token(
    *,
    secret: bytes,
    user_id: UUID,
    search_profile_id: UUID,
    version: int,
    ttl_hours: int,
    now: datetime | None = None,
) -> str:
    """Build an expiring HMAC unsubscribe token (stateless, version-bound)."""
    current = now or datetime.now(timezone.utc)
    exp = int(current.timestamp()) + ttl_hours * 3600
    payload = _token_payload(
        user_id=user_id,
        search_profile_id=search_profile_id,
        version=version,
        exp=exp,
    )
    signature = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def verify_unsubscribe_token(
    *,
    secret: bytes,
    token: str,
    user_id: UUID,
    search_profile_id: UUID,
    version: int,
    now: datetime | None = None,
) -> bool:
    """Verify an unsubscribe token: signature, version match and TTL."""
    try:
        payload, signature = token.rsplit(".", 1)
    except ValueError:
        return False
    expected = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    parts = payload.split("|")
    if len(parts) != 4:
        return False
    token_user, token_search, token_version, token_exp = parts
    if token_user != str(user_id) or token_search != str(search_profile_id):
        return False
    if token_version != str(version):
        return False
    current = (now or datetime.now(timezone.utc)).timestamp()
    try:
        return current < int(token_exp)
    except ValueError:
        return False
