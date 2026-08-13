from __future__ import annotations

from uuid import uuid4

from umbral.infrastructure.queue.rq_queue import RQJobQueue


def test_rq_process_envelope_is_json_serializable_without_a_redis_server() -> None:
    class CapturingQueue:
        def __init__(self) -> None:
            self.serializer = None
            self.arguments: dict[str, object] | None = None

        def enqueue(self, name: str, **kwargs: object) -> None:
            self.arguments = {"function": name, **kwargs}

    queue = RQJobQueue(CapturingQueue())
    execution_id = uuid4()
    correlation_id = uuid4()

    queue.publish(
        execution_id=execution_id,
        attempt_number=1,
        correlation_id=correlation_id,
    )

    serialized = queue.serializer.dumps(queue.queue.arguments)  # type: ignore[no-untyped-call]
    assert queue.queue.serializer.loads(serialized) == {
        "function": "umbral.workers.worker.run_message",
        "execution_id": str(execution_id),
        "attempt_number": 1,
        "correlation_id": str(correlation_id),
        "job_id": f"{execution_id}-1",
    }
