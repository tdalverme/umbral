"""DecisionService handles the domain-level duplicate error (H5)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from umbral.application.events.registry import EventsRegistrySpec
from umbral.application.notifications.contracts import (
    DuplicateDecisionError,
    PlannerDecision,
)
from umbral.application.notifications.decision_service import DecisionService
from umbral.application.notifications.ports import (
    DecisionRepository,
    InboxRepository,
)

_NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)


class _EventWriter:
    def __init__(self) -> None:
        self.events: list[object] = []

    def insert(self, event: object) -> None:
        self.events.append(event)


class _DuplicateOnSecondInsert:
    """Repository fake that races on the second insert attempt."""

    def __init__(self, existing: UUID) -> None:
        self._existing = existing
        self._calls = 0

    def insert(self, **kwargs: object) -> UUID:
        self._calls += 1
        if self._calls > 1:
            raise DuplicateDecisionError
        return uuid4()

    def find_by_item_trigger(self, **kwargs: object) -> UUID | None:
        return self._existing


class _InboxWriter:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add_for_decision(
        self, *, decision_id: object, user_id: object, now: object
    ) -> None:
        self.added.append(decision_id)


class _EventsRegistry:
    def __init__(self) -> None:
        self.event_types = {
            "notification.decision_created.v1": type(
                "T", (), {"version": 1, "required_keys": (), "forbidden_keys": ()}
            )()
        }


def _decision() -> PlannerDecision:
    return PlannerDecision(
        recommendation_item_id=uuid4(),
        search_profile_id=uuid4(),
        trigger="new_match",
        reason_code="criterion_score_above_threshold",
        decision_state="pending_delivery",
    )


def test_duplicate_race_returns_existing_without_re_emitting() -> None:
    existing = uuid4()
    events = _EventWriter()
    inbox = _InboxWriter()
    service = DecisionService(
        decisions=cast(DecisionRepository, _DuplicateOnSecondInsert(existing)),
        inbox=cast(InboxRepository, inbox),
        events_out=events,
        events_registry=cast(EventsRegistrySpec, _EventsRegistry()),
        policy_version="notification-policy-v1",
        clock=lambda: _NOW,
    )
    decision = _decision()
    first = service.record(
        user_id=uuid4(),
        search_profile_id=uuid4(),
        decision=decision,
        inbox_enabled=True,
        now=_NOW,
        correlation_id=uuid4(),
    )
    second = service.record(
        user_id=uuid4(),
        search_profile_id=uuid4(),
        decision=decision,
        inbox_enabled=True,
        now=_NOW,
        correlation_id=uuid4(),
    )
    assert first != second
    assert second == existing
    assert len(events.events) == 1
    assert len(inbox.added) == 1


def test_inbox_item_created_once_when_inbox_enabled() -> None:
    events = _EventWriter()
    inbox = _InboxWriter()
    service = DecisionService(
        decisions=cast(DecisionRepository, _DuplicateOnSecondInsert(uuid4())),
        inbox=cast(InboxRepository, inbox),
        events_out=events,
        events_registry=cast(EventsRegistrySpec, _EventsRegistry()),
        policy_version="notification-policy-v1",
        clock=lambda: _NOW,
    )
    service.record(
        user_id=uuid4(),
        search_profile_id=uuid4(),
        decision=_decision(),
        inbox_enabled=True,
        now=_NOW,
        correlation_id=uuid4(),
    )
    assert len(inbox.added) == 1
    assert len(events.events) == 1


def test_no_inbox_item_when_inbox_disabled() -> None:
    events = _EventWriter()
    inbox = _InboxWriter()
    service = DecisionService(
        decisions=cast(DecisionRepository, _DuplicateOnSecondInsert(uuid4())),
        inbox=cast(InboxRepository, inbox),
        events_out=events,
        events_registry=cast(EventsRegistrySpec, _EventsRegistry()),
        policy_version="notification-policy-v1",
        clock=lambda: _NOW,
    )
    service.record(
        user_id=uuid4(),
        search_profile_id=uuid4(),
        decision=_decision(),
        inbox_enabled=False,
        now=_NOW,
        correlation_id=uuid4(),
    )
    assert len(inbox.added) == 0
    assert len(events.events) == 1
