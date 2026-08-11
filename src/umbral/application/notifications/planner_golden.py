"""Pure parsing and validation of the planner golden dataset (H5)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from pathlib import Path
from uuid import UUID

from umbral.application.notifications.contracts import (
    HistoryDecision,
    NotificationCandidate,
    NotificationPolicy,
    NotificationPreferences,
    PlannerValidationError,
    Trigger,
)

_KNOWN_FAMILIES: frozenset[str] = frozenset(
    {
        "new_match_immediate",
        "new_match_digest",
        "price_drop",
        "duplicate",
        "quiet_hours",
        "fatigue",
        "digest_group",
        "discarded",
        "preferences_disabled",
        "preferences_paused",
        "no_channels",
        "digest_disabled",
    }
)


@dataclass(frozen=True, slots=True)
class GoldenCase:
    """One golden planner case: inputs plus the expected decision."""

    id: str
    family: str
    item: NotificationCandidate
    history: tuple[HistoryDecision, ...]
    preferences: NotificationPreferences
    policy: NotificationPolicy
    now: datetime
    expected_trigger: Trigger
    expected_reason: str
    expected_state: str
    expected_duplicate_of: str | None


@dataclass(frozen=True, slots=True)
class PlannerGoldenDataset:
    """Versioned golden dataset of planner decisions."""

    contract_version: str
    registry_version: str
    reviewed_by: str
    reviewed_at: str
    min_cases_per_family: int
    cases: tuple[GoldenCase, ...] = field(default_factory=tuple)

    def case_by_id(self, case_id: str) -> GoldenCase | None:
        return next((case for case in self.cases if case.id == case_id), None)


def load_golden_dataset(path: Path) -> PlannerGoldenDataset:
    """Load and validate the planner golden dataset from a file path."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise PlannerValidationError("dataset_required")
    return parse_golden_dataset(raw)


def parse_golden_dataset(data: Mapping[str, object]) -> PlannerGoldenDataset:
    """Parse and validate the planner golden document."""
    if data.get("registry_version") != "planner-golden-v1":
        raise PlannerValidationError("registry_version")
    if data.get("contract_version") != "1":
        raise PlannerValidationError("contract_version")
    reviewed_by = data.get("reviewed_by")
    if not isinstance(reviewed_by, str) or not reviewed_by:
        raise PlannerValidationError("reviewed_by_required")
    reviewed_at = data.get("reviewed_at")
    if not isinstance(reviewed_at, str) or not reviewed_at:
        raise PlannerValidationError("reviewed_at_required")
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list):
        raise PlannerValidationError("cases_required")
    cases: list[GoldenCase] = []
    for raw in raw_cases:
        if not isinstance(raw, Mapping):
            raise PlannerValidationError("case_invalid_shape")
        cases.append(_parse_case(raw))
    return PlannerGoldenDataset(
        contract_version="1",
        registry_version="planner-golden-v1",
        reviewed_by=reviewed_by,
        reviewed_at=reviewed_at,
        min_cases_per_family=1,
        cases=tuple(cases),
    )


def _parse_case(raw: Mapping[str, object]) -> GoldenCase:
    case_id = _str(raw, "id")
    family = _str(raw, "family")
    if family not in _KNOWN_FAMILIES:
        raise PlannerValidationError(f"unknown_family:{family}")
    now = _iso(raw.get("now"), "now")
    item = _parse_item(_mapping(raw, "item"))
    raw_history = _list(raw, "history")
    history: list[HistoryDecision] = []
    for entry in raw_history:
        if isinstance(entry, Mapping):
            history.append(_parse_history(entry))
    preferences = _parse_preferences(_mapping(raw, "preferences"))
    policy = _parse_policy_case(_mapping(raw, "policy"))
    expected = _mapping(raw, "expected")
    return GoldenCase(
        id=case_id,
        family=family,
        item=item,
        history=tuple(history),
        preferences=preferences,
        policy=policy,
        now=now,
        expected_trigger=_str(expected, "trigger"),  # type: ignore[arg-type]
        expected_reason=_str(expected, "reason_code"),
        expected_state=_str(expected, "decision_state"),
        expected_duplicate_of=_optional_str(expected.get("duplicate_of_id")),
    )


def _parse_item(raw: Mapping[str, object]) -> NotificationCandidate:
    return NotificationCandidate(
        recommendation_item_id=_uuid(raw, "recommendation_item_id"),
        search_profile_id=_uuid(raw, "search_profile_id"),
        trigger=_str(raw, "trigger"),  # type: ignore[arg-type]
        score=_optional_number(raw.get("score")),
        price_before=_optional_number(raw.get("price_before")),
        price_after=_optional_number(raw.get("price_after")),
        published_at=_iso(raw.get("published_at", raw.get("now")), "published_at"),
    )


def _parse_history(raw: Mapping[str, object]) -> HistoryDecision:
    return HistoryDecision(
        decision_id=_uuid(raw, "decision_id"),
        recommendation_item_id=_uuid(raw, "recommendation_item_id"),
        trigger=_str(raw, "trigger"),  # type: ignore[arg-type]
        decision_state=_str(raw, "decision_state"),
        delivered_at=_optional_iso(raw.get("delivered_at")),
        viewed_at=_optional_iso(raw.get("viewed_at")),
    )


def _parse_preferences(raw: Mapping[str, object]) -> NotificationPreferences:
    return NotificationPreferences(
        email_enabled=bool(raw.get("email_enabled", True)),
        inbox_enabled=bool(raw.get("inbox_enabled", True)),
        timezone=_str(raw, "timezone"),
        quiet_hours_start=_clock(raw.get("quiet_hours_start"), "quiet_hours_start"),
        quiet_hours_end=_clock(raw.get("quiet_hours_end"), "quiet_hours_end"),
        digest_enabled=bool(raw.get("digest_enabled", True)),
        digest_local_hour=_integer(
            raw.get("digest_local_hour", 9), "digest_local_hour"
        ),
        score_threshold=_number(raw.get("score_threshold", 0.6), "score_threshold"),
        state=_str(raw, "state"),  # type: ignore[arg-type]
    )


def _parse_policy_case(raw: Mapping[str, object]) -> NotificationPolicy:
    return NotificationPolicy(
        immediate_score_threshold=_number(
            raw.get("immediate_score_threshold"), "immediate_score_threshold"
        ),
        fatigue_cooldown_hours=_number(
            raw.get("fatigue_cooldown_hours"), "fatigue_cooldown_hours"
        ),
        fatigue_window_hours=_number(
            raw.get("fatigue_window_hours"), "fatigue_window_hours"
        ),
        digest_default_local_hour=_integer(
            raw.get("digest_default_local_hour", 9), "digest_default_local_hour"
        ),
        digest_max_items=_integer(raw.get("digest_max_items", 10), "digest_max_items"),
        quiet_hours_start=_clock(raw.get("quiet_hours_start"), "quiet_hours_start"),
        quiet_hours_end=_clock(raw.get("quiet_hours_end"), "quiet_hours_end"),
    )


def _mapping(raw: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = raw.get(key)
    if not isinstance(value, Mapping):
        raise PlannerValidationError(f"{key}_required")
    return value


def _list(raw: Mapping[str, object], key: str) -> list[object]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise PlannerValidationError(f"{key}_required")
    return value


def _str(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise PlannerValidationError(f"{key}_required")
    return value


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _uuid(raw: Mapping[str, object], key: str) -> UUID:
    value = raw.get(key)
    if not isinstance(value, str):
        raise PlannerValidationError(f"{key}_required")
    try:
        return UUID(value)
    except ValueError:
        raise PlannerValidationError(f"{key}_invalid")


def _iso(value: object, key: str) -> datetime:
    if not isinstance(value, str):
        raise PlannerValidationError(f"{key}_required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise PlannerValidationError(f"{key}_invalid")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _optional_iso(value: object) -> datetime | None:
    return _iso(value, "timestamp") if value is not None else None


def _clock(value: object, key: str) -> time:
    if not isinstance(value, str) or ":" not in value:
        raise PlannerValidationError(f"{key}_invalid")
    try:
        hour, minute = value.split(":")
        return time(int(hour), int(minute))
    except ValueError:
        raise PlannerValidationError(f"{key}_invalid")


def _integer(value: object, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PlannerValidationError(f"{key}_required")
    return value


def _number(value: object, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlannerValidationError(f"{key}_required")
    return float(value)


def _optional_number(value: object) -> float | None:
    if value is None:
        return None
    return _number(value, "number")
