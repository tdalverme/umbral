"""Notification composition root for API and worker processes (H5)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from umbral.application.notifications.decision_service import DecisionService
from umbral.application.notifications.delivery_service import (
    NotificationDeliveryService,
)
from umbral.application.notifications.inbox_service import InboxService
from umbral.application.notifications.planner_service import PlannerService
from umbral.application.notifications.policy import load_policy
from umbral.application.notifications.ports import NotificationEmailPort
from umbral.application.notifications.preferences_service import PreferencesService
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.db.session import SessionProvider
from umbral.infrastructure.notifications.email_adapter import (
    RecordingNotificationEmailAdapter,
    ResendNotificationEmailAdapter,
)
from umbral.infrastructure.notifications.repositories import (
    SqlAlchemyDecisionRepository,
    SqlAlchemyInboxRepository,
    SqlAlchemyPreferenceRepository,
    SqlAlchemyProfileReader,
    SqlAlchemyUserEmailReader,
)
from umbral.infrastructure.radar.contract_loader import load_events_registry

_NOTIFICATIONS_CONTRACTS = (
    Path(__file__).resolve().parents[4] / "contracts" / "notifications" / "v1"
)


def build_notification_services(
    *,
    settings: Settings,
    session_provider: SessionProvider,
    events_out: object,
    email_sender: Callable[..., Any] | None = None,
) -> NotificationServices:
    return NotificationServices(
        settings=settings,
        session_provider=session_provider,
        events_out=events_out,
        email_sender=email_sender,
    )


class NotificationServices:
    """Composed notification services shared by API and workers."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_provider: SessionProvider,
        events_out: object,
        email_sender: Callable[..., Any] | None = None,
    ) -> None:
        session_factory = session_provider.session_factory
        events_registry = load_events_registry()
        policy = load_policy(
            _NOTIFICATIONS_CONTRACTS / f"{settings.notifications_policy_version}.json"
        )

        def clock() -> datetime:
            return datetime.now(timezone.utc)

        preferences_repo = SqlAlchemyPreferenceRepository(session_factory)
        decisions_repo = SqlAlchemyDecisionRepository(session_factory)
        inbox_repo = SqlAlchemyInboxRepository(session_factory)
        profiles = SqlAlchemyProfileReader(session_factory)
        user_email = SqlAlchemyUserEmailReader(session_factory)

        if email_sender is not None:
            email: NotificationEmailPort = ResendNotificationEmailAdapter(
                sender_email=settings.notifications_email_from,
                sender=email_sender,
            )
        else:
            email = RecordingNotificationEmailAdapter()

        self.profiles = profiles
        self.preferences = PreferencesService(
            repository=preferences_repo,
            default_timezone=settings.notifications_default_timezone,
        )
        self.decision_service = DecisionService(
            decisions=decisions_repo,
            inbox=inbox_repo,
            events_out=events_out,
            events_registry=events_registry,
            policy_version=settings.notifications_policy_version,
            clock=clock,
        )
        self.inbox = InboxService(
            repository=inbox_repo,
            events_out=events_out,
            events_registry=events_registry,
            clock=clock,
        )
        self.delivery = NotificationDeliveryService(
            decisions=decisions_repo,
            email=email,
            user_email=user_email,
            events_out=events_out,
            events_registry=events_registry,
            email_from=settings.notifications_email_from,
            clock=clock,
        )
        self.planner = PlannerService(
            decisions=decisions_repo,
            decision_service=self.decision_service,
            preferences=self.preferences,
            profiles=profiles,
            delivery=self.delivery,
            policy=policy,
        )
