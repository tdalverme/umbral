"""Delivery service: send one decision by email idempotently (H5, UM-H5-011..).

Delivering reads the decision, sends the grounded email via the adapter and
marks it delivered with the provider message id. The state transition
(pending_delivery -> delivered) is the idempotency guard; a failure leaves
the decision retryable (the scheduler duty re-enters it).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from uuid import UUID, uuid4

from umbral.application.events.contracts import ProductEvent
from umbral.application.events.registry import EventsRegistrySpec, event_version
from umbral.application.notifications.ports import (
    DecisionRepository,
    NotificationEmailPort,
    UserEmailReader,
)

_DELIVERED_EVENT = "notification.delivered.v1"
_FAILED_EVENT = "notification.delivery_failed.v1"


class NotificationDeliveryService:
    """Delivers one pending decision by email; idempotent by state."""

    def __init__(
        self,
        *,
        decisions: DecisionRepository,
        email: NotificationEmailPort,
        user_email: UserEmailReader,
        events_out: object,
        events_registry: EventsRegistrySpec,
        email_from: str,
        clock: Callable[[], datetime],
    ) -> None:
        self._decisions = decisions
        self._email = email
        self._user_email = user_email
        self._events_out = events_out
        self._events_registry = events_registry
        self._email_from = email_from
        self._clock = clock

    def deliver_decision(
        self, *, decision_id: UUID, now: datetime, correlation_id: UUID
    ) -> bool:
        decision = self._decisions.get(decision_id)
        if decision is None:
            return False
        if decision.get("decision_state") not in {"pending_delivery", "pending_digest"}:
            return False
        user_id = decision.get("user_id")
        user_uuid = user_id if isinstance(user_id, UUID) else None
        to_email = self._user_email.email_for(user_uuid) if user_uuid else None
        if not to_email:
            self._emit_failed(
                decision_id=decision_id,
                channel="email",
                error_code="notifications.recipient_missing",
                correlation_id=correlation_id,
            )
            return False
        provider_message_id = f"{decision_id}-{now.timestamp():.0f}"
        subject = "Nueva oportunidad en tu radar de Umbral"
        body_html = _render_decision(decision, self._email_from)
        try:
            message_id = self._email.send_decision_email(
                to_email=to_email,
                subject=subject,
                body_html=body_html,
                decision_id=decision_id,
                provider_message_id=provider_message_id,
                now=now,
                correlation_id=correlation_id,
            )
        except Exception as exc:  # noqa: BLE001 - typed provider failure
            self._emit_failed(
                decision_id=decision_id,
                channel="email",
                error_code=getattr(exc, "code", "email.provider_unavailable"),
                correlation_id=correlation_id,
            )
            return False
        marked = self._decisions.mark_delivered(
            decision_id=decision_id, provider_message_id=message_id, now=now
        )
        if marked:
            self._emit_delivered(
                decision_id=decision_id,
                channel="email",
                provider_message_id=message_id,
                correlation_id=correlation_id,
            )
        return marked

    def _emit_delivered(
        self,
        *,
        decision_id: UUID,
        channel: str,
        provider_message_id: str,
        correlation_id: UUID,
    ) -> None:
        event = ProductEvent(
            event_id=uuid4(),
            event_type=_DELIVERED_EVENT,
            event_version=event_version(self._events_registry, _DELIVERED_EVENT) or 1,
            actor_id=None,
            occurred_at=self._clock(),
            correlation_id=correlation_id,
            payload={
                "decision_id": str(decision_id),
                "channel": channel,
                "provider_message_id": provider_message_id,
            },
        )
        self._events_out.insert(event)  # type: ignore[attr-defined]

    def _emit_failed(
        self,
        *,
        decision_id: UUID,
        channel: str,
        error_code: str,
        correlation_id: UUID,
    ) -> None:
        event = ProductEvent(
            event_id=uuid4(),
            event_type=_FAILED_EVENT,
            event_version=event_version(self._events_registry, _FAILED_EVENT) or 1,
            actor_id=None,
            occurred_at=self._clock(),
            correlation_id=correlation_id,
            payload={
                "decision_id": str(decision_id),
                "channel": channel,
                "error_code": error_code,
            },
        )
        self._events_out.insert(event)  # type: ignore[attr-defined]


def _render_decision(
    decision: Mapping[str, object], email_from: str
) -> str:
    reason = str(decision.get("reason_code", ""))
    title = (
        "Nueva oportunidad"
        if decision.get("trigger") == "new_match"
        else "Baja de precio"
    )
    return (
        "<div>"
        f"<h2>{title}</h2>"
        f"<p>Una oportunidad de tu radar supero los filtros.</p>"
        f"<p>Razon: {reason}</p>"
        f"<p>Abri tu radar para verla: tu centro de notificaciones.</p>"
        f"<p><small>{email_from}</small></p>"
        "</div>"
    )
