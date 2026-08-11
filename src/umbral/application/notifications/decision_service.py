"""Decision service: persist planner decisions, dedupe and inbox items (H5)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid4

from umbral.application.events.contracts import ProductEvent
from umbral.application.events.registry import EventsRegistrySpec, event_version
from umbral.application.notifications.contracts import PlannerDecision
from umbral.application.notifications.ports import (
    DecisionRepository,
    InboxRepository,
)

_NOTIFICATION_EVENT = "notification.decision_created.v1"


class DecisionService:
    """Persist one planner decision idempotently and create its inbox view."""

    def __init__(
        self,
        *,
        decisions: DecisionRepository,
        inbox: InboxRepository,
        events_out: object,
        events_registry: EventsRegistrySpec,
        policy_version: str,
        clock: Callable[[], datetime],
    ) -> None:
        self._decisions = decisions
        self._inbox = inbox
        self._events_out = events_out
        self._events_registry = events_registry
        self._policy_version = policy_version
        self._clock = clock

    def record(
        self,
        *,
        user_id: UUID,
        search_profile_id: UUID,
        decision: PlannerDecision,
        inbox_enabled: bool,
        now: datetime,
        correlation_id: UUID,
    ) -> UUID:
        decision_id = self._decisions.insert(
            user_id=user_id,
            search_profile_id=search_profile_id,
            recommendation_item_id=decision.recommendation_item_id,
            trigger=decision.trigger,
            reason_code=decision.reason_code,
            decision_state=decision.decision_state,
            policy_version=self._policy_version,
            preferences_version=1,
            price_before=None,
            price_after=None,
            duplicate_of_id=decision.duplicate_of_id,
            now=now,
            correlation_id=correlation_id,
        )
        self._emit_decision_created(
            decision_id=decision_id,
            search_profile_id=search_profile_id,
            decision=decision,
            correlation_id=correlation_id,
        )
        return decision_id

    def _emit_decision_created(
        self,
        *,
        decision_id: UUID,
        search_profile_id: UUID,
        decision: PlannerDecision,
        correlation_id: UUID,
    ) -> None:
        event = ProductEvent(
            event_id=uuid4(),
            event_type=_NOTIFICATION_EVENT,
            event_version=(
                event_version(self._events_registry, _NOTIFICATION_EVENT) or 1
            ),
            actor_id=None,
            occurred_at=self._clock(),
            correlation_id=correlation_id,
            payload={
                "decision_id": str(decision_id),
                "search_profile_id": str(search_profile_id),
                "trigger": decision.trigger,
                "reason_code": decision.reason_code,
                "decision_state": decision.decision_state,
            },
        )
        self._events_out.insert(event)  # type: ignore[attr-defined]
