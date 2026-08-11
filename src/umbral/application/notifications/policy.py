"""Pure parsing of the versioned notification policy contract (H5)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import time
from pathlib import Path

from umbral.application.notifications.contracts import (
    NotificationPolicy,
    PlannerValidationError,
)


def load_policy(path: Path) -> NotificationPolicy:
    """Load and validate the notification policy from a file path."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise PlannerValidationError("policy_required")
    return parse_policy(raw)


def parse_policy(data: Mapping[str, object]) -> NotificationPolicy:
    """Parse and validate a policy document; raises on the first group."""
    if data.get("registry_version") != "notification-policy-v1":
        raise PlannerValidationError("registry_version")
    if data.get("contract_version") != "1":
        raise PlannerValidationError("contract_version")
    threshold = _number(data.get("immediate_score_threshold"), "threshold")
    cooldown = _number(data.get("fatigue_cooldown_hours"), "cooldown")
    window = _number(data.get("fatigue_window_hours"), "window")
    digest_hour = _integer(data.get("digest_default_local_hour"), "digest_hour")
    max_items = _integer(data.get("digest_max_items"), "max_items")
    if not (0.0 <= threshold <= 1.0):
        raise PlannerValidationError("threshold_range")
    if cooldown <= 0 or window <= 0:
        raise PlannerValidationError("fatigue_range")
    if not (0 <= digest_hour <= 23):
        raise PlannerValidationError("digest_hour_range")
    if max_items <= 0:
        raise PlannerValidationError("max_items_range")
    return NotificationPolicy(
        immediate_score_threshold=threshold,
        fatigue_cooldown_hours=cooldown,
        fatigue_window_hours=window,
        digest_default_local_hour=digest_hour,
        digest_max_items=max_items,
        quiet_hours_start=_time(data.get("quiet_hours_start"), "quiet_hours_start"),
        quiet_hours_end=_time(data.get("quiet_hours_end"), "quiet_hours_end"),
    )


def _number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlannerValidationError(f"{field_name}_required")
    return float(value)


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PlannerValidationError(f"{field_name}_required")
    return value


def _time(value: object, field_name: str) -> time:
    if not isinstance(value, str) or ":" not in value:
        raise PlannerValidationError(f"{field_name}_invalid")
    try:
        hour, minute = value.split(":")
        return time(int(hour), int(minute))
    except ValueError:
        raise PlannerValidationError(f"{field_name}_invalid")
