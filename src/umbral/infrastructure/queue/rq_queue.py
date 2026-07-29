"""RQ adapter configured for JSON-only transport payloads."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from rq.serializers import JSONSerializer


class RQJobQueue:
    def __init__(
        self,
        queue: Any,
        *,
        job_name: str = "umbral.workers.worker:run_message",
    ) -> None:
        self.queue = queue
        self.job_name = job_name
        # RQ permits an injected serializer. Replace a pickle serializer at
        # this seam so ORM objects/secrets can never enter a message payload.
        if not isinstance(getattr(queue, "serializer", None), JSONSerializer):
            try:
                queue.serializer = JSONSerializer()
            except (AttributeError, TypeError):
                pass

    @classmethod
    def from_connection(
        cls,
        connection: Any,
        *,
        name: str = "umbral",
        job_name: str = "umbral.workers.worker:run_message",
    ) -> RQJobQueue:
        from rq import Queue

        return cls(
            Queue(name=name, connection=connection, serializer=JSONSerializer()),
            job_name=job_name,
        )

    def publish(
        self,
        *,
        execution_id: UUID,
        attempt_number: int,
        correlation_id: UUID,
    ) -> str:
        if attempt_number < 1:
            raise ValueError("attempt_number must be positive")
        message_id = f"{execution_id}:{attempt_number}"
        self.queue.enqueue(
            self.job_name,
            execution_id=str(execution_id),
            attempt_number=attempt_number,
            correlation_id=str(correlation_id),
            job_id=message_id,
        )
        return message_id
