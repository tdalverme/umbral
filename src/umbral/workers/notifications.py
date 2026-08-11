"""Durable notification duties and delivery job (H5).

- ``notifications.plan``: scheduler duty that plans new items of active
  profiles and records decisions (idempotent by item+trigger).
- ``notifications.digest``: scheduler duty that materializes digest decisions.
- ``notifications.deliver``: RQ job that delivers one decision via the email
  adapter with provider-message-id idempotency.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from uuid import UUID

from umbral.application.jobs.contracts import (
    JobContext,
    JsonScalar,
    PermanentJobError,
    TransientJobError,
)
from umbral.application.notifications.delivery_service import (
    NotificationDeliveryService,
)
from umbral.application.notifications.planner_service import PlannerService
from umbral.workers.registry import JobRegistry


class NotificationDeliverHandler:
    """Delivers one decision; the queue payload carries only the decision id."""

    job_type = "notifications.deliver"

    def __init__(self, delivery: NotificationDeliveryService) -> None:
        self._delivery = delivery

    def normalize_target(self, raw_target: str) -> str:
        return str(UUID(raw_target))

    def run(self, context: JobContext) -> Mapping[str, JsonScalar]:
        decision_id = UUID(str(context.logical_target))
        try:
            delivered = self._delivery.deliver_decision(
                decision_id=decision_id,
                now=datetime.now(timezone.utc),
                correlation_id=context.correlation_id,
            )
        except TransientJobError:
            raise
        except Exception as exc:  # noqa: BLE001 - typed below
            raise PermanentJobError("notifications.deliver_failed") from exc
        return {"decision_id": str(decision_id), "delivered": delivered}


def build_plan_duty(planner: PlannerService) -> Callable[[datetime], int]:
    """Build the scheduler duty that plans new items (bounded per pass)."""

    def plan_all(now: datetime) -> int:
        return planner.plan_all(now=now)

    return plan_all


def build_digest_duty(planner: PlannerService) -> Callable[[datetime], int]:
    """Build the scheduler duty that materializes digest decisions."""

    def digest(now: datetime) -> int:
        return planner.digest_all(now=now)

    return digest


def build_notifications_registry(
    delivery: NotificationDeliveryService,
) -> JobRegistry:
    """Compose the explicit notification job registry without dynamic imports."""

    return JobRegistry(
        {
            "notifications.deliver": NotificationDeliverHandler(delivery),
        }
    )
