# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Scheduler pass idempotency: repeated plan passes never duplicate (H5)."""

from __future__ import annotations

from datetime import datetime, timezone

from umbral.application.notifications.contracts import NotificationCandidate
from umbral.application.notifications.decision_service import DecisionService
from umbral.application.notifications.planner import plan
from umbral.application.notifications.planner_service import PlannerService
from umbral.application.notifications.policy import load_policy
from umbral.application.notifications.preferences_service import PreferencesService
from umbral.infrastructure.notifications.repositories import (
    SqlAlchemyProfileReader,
)

_NOW = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)


class _EventWriter:
    def __init__(self) -> None:
        self.events: list[object] = []

    def insert(self, event: object) -> None:
        self.events.append(event)


def _services(notification_repos, factory):
    from umbral.infrastructure.radar.contract_loader import load_events_registry

    events_out = _EventWriter()
    events_registry = load_events_registry()
    prefs = PreferencesService(
        repository=notification_repos["preferences"],
        default_timezone="America/Argentina/Buenos_Aires",
    )
    decisions = notification_repos["decisions"]
    decision_service = DecisionService(
        decisions=decisions,
        inbox=object(),  # type: ignore[arg-type]
        events_out=events_out,
        events_registry=events_registry,
        policy_version="notification-policy-v1",
        clock=lambda: _NOW,
    )
    policy = load_policy(
        Path("contracts/notifications/v1/notification-policy-v1.json")
    )
    planner = PlannerService(
        decisions=decisions,
        decision_service=decision_service,
        preferences=prefs,
        profiles=SqlAlchemyProfileReader(factory),
        delivery=object(),  # type: ignore[arg-type]
        policy=policy,
    )
    return prefs, decisions, decision_service, planner, events_out


from pathlib import Path  # noqa: E402


def test_repeated_plan_pass_is_idempotent(
    notification_repos, notification_seed
) -> None:
    prefs, decisions, decision_service, planner, _events = _services(
        notification_repos, notification_seed["factory"]
    )
    candidate = NotificationCandidate(
        recommendation_item_id=notification_seed["recommendation_item_id"],
        search_profile_id=notification_seed["search_profile_id"],
        trigger="new_match",
        score=0.9,
        published_at=_NOW,
    )
    first = planner.plan_profile(
        user_id=notification_seed["user_id"],
        search_profile_id=notification_seed["search_profile_id"],
        candidates=(candidate,),
        now=_NOW,
        correlation_id=notification_seed["search_profile_id"],
    )
    assert first == 1
    second = planner.plan_profile(
        user_id=notification_seed["user_id"],
        search_profile_id=notification_seed["search_profile_id"],
        candidates=(candidate,),
        now=_NOW,
        correlation_id=notification_seed["search_profile_id"],
    )
    assert second == 0


def test_record_is_idempotent_on_unique_race(
    notification_repos, notification_seed
) -> None:
    _prefs, decisions, decision_service, _planner, events = _services(
        notification_repos, notification_seed["factory"]
    )
    decision = plan(
        candidate=NotificationCandidate(
            recommendation_item_id=notification_seed["recommendation_item_id"],
            search_profile_id=notification_seed["search_profile_id"],
            trigger="price_drop",
            score=0.8,
            price_before=1000.0,
            price_after=800.0,
            published_at=_NOW,
        ),
        history=(),
        preferences=prefs_for(notification_repos, notification_seed),
        policy=load_policy(Path("contracts/notifications/v1/notification-policy-v1.json")),
        now=_NOW,
    )
    first = decision_service.record(
        user_id=notification_seed["user_id"],
        search_profile_id=notification_seed["search_profile_id"],
        decision=decision,
        inbox_enabled=True,
        now=_NOW,
        correlation_id=notification_seed["search_profile_id"],
    )
    second = decision_service.record(
        user_id=notification_seed["user_id"],
        search_profile_id=notification_seed["search_profile_id"],
        decision=decision,
        inbox_enabled=True,
        now=_NOW,
        correlation_id=notification_seed["search_profile_id"],
    )
    assert second == first
    assert len(events.events) == 1


def prefs_for(notification_repos, notification_seed):
    from umbral.application.notifications.contracts import NotificationPreferences

    return notification_repos["preferences"].get(
        user_id=notification_seed["user_id"],
        search_profile_id=notification_seed["search_profile_id"],
    ) or NotificationPreferences()
