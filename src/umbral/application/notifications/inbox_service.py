"""Inbox service: list decisions and mark read (H5, UM-H5-015/016)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from uuid import UUID, uuid4

from umbral.application.events.contracts import ProductEvent
from umbral.application.events.registry import EventsRegistrySpec, event_version
from umbral.application.notifications.ports import InboxRepository

_VIEWED_EVENT = "notification.viewed.v1"


class InboxService:
    """Ownership-scoped inbox with viewed/acted event emission."""

    def __init__(
        self,
        *,
        repository: InboxRepository,
        events_out: object,
        events_registry: EventsRegistrySpec,
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._events_out = events_out
        self._events_registry = events_registry
        self._clock = clock

    def list_for_user(
        self, *, user_id: UUID, limit: int, after: object | None = None
    ) -> Sequence[Mapping[str, object]]:
        return self._repository.list_for_user(user_id=user_id, limit=limit, after=after)

    def mark_read(
        self, *, user_id: UUID, decision_id: UUID, correlation_id: UUID
    ) -> bool:
        updated = self._repository.mark_read(
            user_id=user_id, decision_id=decision_id, now=self._clock()
        )
        if updated:
            self._emit(
                _VIEWED_EVENT, decision_id=decision_id, correlation_id=correlation_id
            )
        return updated

    def _emit(
        self, event_type: str, *, decision_id: UUID, correlation_id: UUID
    ) -> None:
        event = ProductEvent(
            event_id=uuid4(),
            event_type=event_type,
            event_version=event_version(self._events_registry, event_type) or 1,
            actor_id=None,
            occurred_at=self._clock(),
            correlation_id=correlation_id,
            payload={"decision_id": str(decision_id)},
        )
        self._events_out.insert(event)  # type: ignore[attr-defined]
