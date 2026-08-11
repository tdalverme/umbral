"""Deterministic notification planner (H5, UM-H5-003..UM-H5-010).

Pure function: 0 network, 0 DB, 0 LLM. Given a candidate item, prior
decisions, preferences and the versioned policy, it returns exactly one
decision with a machine-checkable reason code. The golden dataset gates any
change to this module.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from umbral.application.notifications.contracts import (
    HistoryDecision,
    NotificationCandidate,
    NotificationPolicy,
    NotificationPreferences,
    PlannerDecision,
)
from umbral.application.notifications.planner_golden import GoldenCase

_DISCARDED_STATES = frozenset({"discarded", "duplicated"})


def plan(
    *,
    candidate: NotificationCandidate,
    history: tuple[HistoryDecision, ...],
    preferences: NotificationPreferences,
    policy: NotificationPolicy,
    now: datetime,
) -> PlannerDecision:
    """Evaluate one candidate and return its notification decision."""
    if preferences.state == "disabled":
        return _decide(candidate, "preferences_disabled", "discarded")
    if preferences.state == "paused":
        return _decide(candidate, "preferences_paused", "postponed")
    duplicate = _find_duplicate(candidate, history)
    if duplicate is not None:
        return _decide(
            candidate, "duplicate", "duplicated", duplicate_of_id=duplicate
        )
    if _in_quiet_hours(preferences, now):
        return _decide(candidate, "quiet_hours", "postponed")
    if _in_fatigue_cooldown(history, policy, now):
        return _decide(candidate, "fatigue", "postponed")
    if not preferences.email_enabled and not preferences.inbox_enabled:
        return _decide(candidate, "no_channels", "discarded")
    if candidate.trigger == "price_drop":
        return _decide(candidate, "price_drop", "pending_delivery")
    score = candidate.score
    if score is None or score < preferences.score_threshold:
        if not preferences.digest_enabled:
            return _decide(candidate, "digest_disabled", "discarded")
        return _decide(candidate, "digest", "pending_digest")
    return _decide(candidate, "new_match", "pending_delivery")


def _decide(
    candidate: NotificationCandidate,
    reason: str,
    state: str,
    duplicate_of_id: object | None = None,
) -> PlannerDecision:
    duplicate = duplicate_of_id if isinstance(duplicate_of_id, UUID) else None
    return PlannerDecision(
        recommendation_item_id=candidate.recommendation_item_id,
        search_profile_id=candidate.search_profile_id,
        trigger=candidate.trigger,
        reason_code=reason,
        decision_state=state,  # type: ignore[arg-type]
        duplicate_of_id=duplicate,
    )


def _find_duplicate(
    candidate: NotificationCandidate, history: tuple[HistoryDecision, ...]
) -> object | None:
    for prior in history:
        if (
            prior.recommendation_item_id == candidate.recommendation_item_id
            and prior.trigger == candidate.trigger
            and prior.decision_state not in _DISCARDED_STATES
        ):
            return prior.decision_id
    return None


def _in_quiet_hours(
    preferences: NotificationPreferences, now: datetime
) -> bool:
    try:
        local = now.astimezone(ZoneInfo(preferences.timezone))
    except Exception:  # noqa: BLE001 - invalid timezone treated as not quiet
        return False
    local_time = local.time().replace(tzinfo=None)
    start = preferences.quiet_hours_start
    end = preferences.quiet_hours_end
    if start == end:
        return False
    if start < end:
        return start <= local_time < end
    # overnight range (e.g. 22:00 -> 08:00)
    return local_time >= start or local_time < end


def _in_fatigue_cooldown(
    history: tuple[HistoryDecision, ...],
    policy: NotificationPolicy,
    now: datetime,
) -> bool:
    cooldown = timedelta(hours=policy.fatigue_cooldown_hours)
    for prior in history:
        if prior.delivered_at is None:
            continue
        if prior.viewed_at is not None:
            continue
        if prior.decision_state not in {"delivered", "read"}:
            continue
        if now - prior.delivered_at <= cooldown:
            return True
    return False


def golden_verdict(case: GoldenCase) -> tuple[bool, str]:
    """Run one golden case through the planner and compare to expectation."""
    decision = plan(
        candidate=case.item,
        history=case.history,
        preferences=case.preferences,
        policy=case.policy,
        now=case.now,
    )
    if decision.trigger != case.expected_trigger:
        return False, f"trigger {decision.trigger} != {case.expected_trigger}"
    if decision.reason_code != case.expected_reason:
        return False, f"reason {decision.reason_code} != {case.expected_reason}"
    if decision.decision_state != case.expected_state:
        return False, f"state {decision.decision_state} != {case.expected_state}"
    if decision.duplicate_of_id is None and case.expected_duplicate_of is not None:
        return False, "expected duplicate reference"
    if (
        decision.duplicate_of_id is not None
        and str(decision.duplicate_of_id) != case.expected_duplicate_of
    ):
        return False, "duplicate reference mismatch"
    return True, "ok"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
