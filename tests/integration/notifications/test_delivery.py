# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Notification persistence and delivery integration tests (H5)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from umbral.application.notifications.contracts import NotificationPreferences
from umbral.application.notifications.delivery_service import (
    NotificationDeliveryService,
)
from umbral.infrastructure.notifications.email_adapter import (
    RecordingNotificationEmailAdapter,
)

_NOW = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)


class _EventWriter:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def insert(self, event: object) -> None:
        self.events.append({"event_type": getattr(event, "event_type")})


def test_preferences_upsert_bumps_version(
    notification_repos, notification_seed
) -> None:
    prefs_repo = notification_repos["preferences"]
    user_id = notification_seed["user_id"]
    search_id = notification_seed["search_profile_id"]
    first = NotificationPreferences()
    stored = prefs_repo.upsert(
        user_id=user_id,
        search_profile_id=search_id,
        preferences=first,
        now=_NOW,
        correlation_id=uuid4(),
    )
    assert stored.version == first.version
    loaded = prefs_repo.get(user_id=user_id, search_profile_id=search_id)
    assert loaded is not None
    assert loaded.email_enabled is True
    second = NotificationPreferences(version=2, email_enabled=False)
    prefs_repo.upsert(
        user_id=user_id,
        search_profile_id=search_id,
        preferences=second,
        now=_NOW,
        correlation_id=uuid4(),
    )
    loaded_after = prefs_repo.get(user_id=user_id, search_profile_id=search_id)
    assert loaded_after is not None
    assert loaded_after.email_enabled is False
    assert loaded_after.version == 2


def test_delivery_marks_delivered_once(notification_repos, notification_seed) -> None:
    decisions = notification_repos["decisions"]
    user_id = notification_seed["user_id"]
    search_id = notification_seed["search_profile_id"]
    item_id = notification_seed["recommendation_item_id"]
    decision_id = decisions.insert(
        user_id=user_id,
        search_profile_id=search_id,
        recommendation_item_id=item_id,
        trigger="new_match",
        reason_code="new_match",
        decision_state="pending_delivery",
        policy_version="notification-policy-v1",
        preferences_version=1,
        price_before=None,
        price_after=None,
        duplicate_of_id=None,
        now=_NOW,
        correlation_id=uuid4(),
    )
    email = RecordingNotificationEmailAdapter()
    events = _EventWriter()
    from umbral.infrastructure.radar.contract_loader import load_events_registry

    class _Emails:
        def email_for(self, uid: object) -> str | None:
            return "usuario@example.test"

    delivery = NotificationDeliveryService(
        decisions=decisions,
        email=email,
        user_email=_Emails(),
        events_out=events,
        events_registry=load_events_registry(),
        email_from="Umbral <alertas@umbral.local>",
        clock=lambda: _NOW,
    )
    first = delivery.deliver_decision(
        decision_id=decision_id, now=_NOW, correlation_id=uuid4()
    )
    assert first is True
    second = delivery.deliver_decision(
        decision_id=decision_id, now=_NOW, correlation_id=uuid4()
    )
    assert second is False
    assert len(email.messages) == 1
    assert any(e["event_type"] == "notification.delivered.v1" for e in events.events)


def test_delivery_failure_leaves_decision_retryable(
    notification_repos, notification_seed
) -> None:
    decisions = notification_repos["decisions"]
    user_id = notification_seed["user_id"]
    search_id = notification_seed["search_profile_id"]
    decision_id = decisions.insert(
        user_id=user_id,
        search_profile_id=search_id,
        recommendation_item_id=notification_seed["recommendation_item_id"],
        trigger="price_drop",
        reason_code="price_drop",
        decision_state="pending_delivery",
        policy_version="notification-policy-v1",
        preferences_version=1,
        price_before=1000.0,
        price_after=800.0,
        duplicate_of_id=None,
        now=_NOW,
        correlation_id=uuid4(),
    )
    email = RecordingNotificationEmailAdapter()
    email.fail_send = True
    events = _EventWriter()
    from umbral.infrastructure.radar.contract_loader import load_events_registry

    class _Emails:
        def email_for(self, uid: object) -> str | None:
            return "usuario@example.test"

    delivery = NotificationDeliveryService(
        decisions=decisions,
        email=email,
        user_email=_Emails(),
        events_out=events,
        events_registry=load_events_registry(),
        email_from="Umbral <alertas@umbral.local>",
        clock=lambda: _NOW,
    )
    delivered = delivery.deliver_decision(
        decision_id=decision_id, now=_NOW, correlation_id=uuid4()
    )
    assert delivered is False
    assert any(
        e["event_type"] == "notification.delivery_failed.v1" for e in events.events
    )
    row = decisions.get(decision_id)
    assert row is not None
    assert row["decision_state"] == "pending_delivery"
