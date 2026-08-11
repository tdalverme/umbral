"""Deterministic planner unit tests beyond the golden gate (H5)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from umbral.application.notifications.contracts import (
    HistoryDecision,
    NotificationCandidate,
    NotificationPolicy,
    NotificationPreferences,
)
from umbral.application.notifications.planner import plan

_POLICY = NotificationPolicy()
_PREFS = NotificationPreferences()
_NOW = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)


def _candidate(**overrides: object) -> NotificationCandidate:
    values: dict[str, object] = {
        "recommendation_item_id": uuid4(),
        "search_profile_id": uuid4(),
        "trigger": "new_match",
        "score": 0.9,
        "published_at": _NOW,
    }
    values.update(overrides)
    return NotificationCandidate(**values)  # type: ignore[arg-type]


def test_disabled_preferences_discard() -> None:
    prefs = NotificationPreferences(state="disabled")
    decision = plan(
        candidate=_candidate(),
        history=(),
        preferences=prefs,
        policy=_POLICY,
        now=_NOW,
    )
    assert decision.decision_state == "discarded"
    assert decision.reason_code == "preferences_disabled"


def test_paused_preferences_postpone() -> None:
    prefs = NotificationPreferences(state="paused")
    decision = plan(
        candidate=_candidate(),
        history=(),
        preferences=prefs,
        policy=_POLICY,
        now=_NOW,
    )
    assert decision.decision_state == "postponed"
    assert decision.reason_code == "preferences_paused"


def test_quiet_hours_postpone_in_overnight_range() -> None:
    now = datetime(2026, 8, 11, 1, 0, tzinfo=timezone.utc)  # 22:00 local (-3)
    decision = plan(
        candidate=_candidate(),
        history=(),
        preferences=_PREFS,
        policy=_POLICY,
        now=now,
    )
    assert decision.decision_state == "postponed"
    assert decision.reason_code == "quiet_hours"


def test_fatigue_cooldown_postpones_unviewed_delivery() -> None:
    prior_id = uuid4()
    history = (
        HistoryDecision(
            decision_id=prior_id,
            recommendation_item_id=uuid4(),
            trigger="new_match",
            decision_state="delivered",
            delivered_at=datetime(2026, 8, 11, 13, 0, tzinfo=timezone.utc),
            viewed_at=None,
        ),
    )
    decision = plan(
        candidate=_candidate(),
        history=history,
        preferences=_PREFS,
        policy=_POLICY,
        now=_NOW,
    )
    assert decision.reason_code == "fatigue"
    assert decision.decision_state == "postponed"


def test_viewed_delivery_clears_fatigue() -> None:
    history = (
        HistoryDecision(
            decision_id=uuid4(),
            recommendation_item_id=uuid4(),
            trigger="new_match",
            decision_state="delivered",
            delivered_at=datetime(2026, 8, 11, 13, 0, tzinfo=timezone.utc),
            viewed_at=datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc),
        ),
    )
    decision = plan(
        candidate=_candidate(),
        history=history,
        preferences=_PREFS,
        policy=_POLICY,
        now=_NOW,
    )
    assert decision.reason_code == "new_match"
    assert decision.decision_state == "pending_delivery"


def test_duplicate_references_prior_decision() -> None:
    item_id = uuid4()
    prior_id = uuid4()
    history = (
        HistoryDecision(
            decision_id=prior_id,
            recommendation_item_id=item_id,
            trigger="new_match",
            decision_state="pending_delivery",
        ),
    )
    decision = plan(
        candidate=_candidate(recommendation_item_id=item_id),
        history=history,
        preferences=_PREFS,
        policy=_POLICY,
        now=_NOW,
    )
    assert decision.reason_code == "duplicate"
    assert decision.decision_state == "duplicated"
    assert decision.duplicate_of_id == prior_id


def test_low_score_goes_to_digest() -> None:
    decision = plan(
        candidate=_candidate(score=0.5),
        history=(),
        preferences=_PREFS,
        policy=_POLICY,
        now=_NOW,
    )
    assert decision.decision_state == "pending_digest"
    assert decision.reason_code == "digest"


def test_price_drop_is_immediate() -> None:
    decision = plan(
        candidate=_candidate(trigger="price_drop", score=0.5),
        history=(),
        preferences=_PREFS,
        policy=_POLICY,
        now=_NOW,
    )
    assert decision.decision_state == "pending_delivery"
    assert decision.reason_code == "price_drop"


def test_no_channels_discards() -> None:
    prefs = NotificationPreferences(email_enabled=False, inbox_enabled=False)
    decision = plan(
        candidate=_candidate(),
        history=(),
        preferences=prefs,
        policy=_POLICY,
        now=_NOW,
    )
    assert decision.reason_code == "no_channels"
    assert decision.decision_state == "discarded"


def test_digest_disabled_discards_low_score() -> None:
    prefs = NotificationPreferences(digest_enabled=False)
    decision = plan(
        candidate=_candidate(score=0.5),
        history=(),
        preferences=prefs,
        policy=_POLICY,
        now=_NOW,
    )
    assert decision.reason_code == "digest_disabled"
    assert decision.decision_state == "discarded"


def test_unknown_score_goes_to_digest() -> None:
    decision = plan(
        candidate=_candidate(score=None),
        history=(),
        preferences=_PREFS,
        policy=_POLICY,
        now=_NOW,
    )
    assert decision.decision_state == "pending_digest"


def test_invalid_timezone_is_not_quiet() -> None:
    prefs = NotificationPreferences(timezone="Not/AZone")
    decision = plan(
        candidate=_candidate(),
        history=(),
        preferences=prefs,
        policy=_POLICY,
        now=_NOW,
    )
    assert decision.reason_code == "new_match"
