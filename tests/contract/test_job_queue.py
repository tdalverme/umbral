from __future__ import annotations

import json
from uuid import uuid4

import pytest

from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.infrastructure.queue.rq_queue import RQJobQueue


def test_recording_queue_keeps_ids_only_and_is_json_serializable() -> None:
    execution_id = uuid4()
    correlation_id = uuid4()
    queue = RecordingJobQueue()

    message_id = queue.publish(
        execution_id=execution_id,
        attempt_number=1,
        correlation_id=correlation_id,
    )

    assert message_id == f"{execution_id}-1"
    payload = queue.messages[0].payload
    assert payload == {
        "execution_id": str(execution_id),
        "attempt_number": 1,
        "correlation_id": str(correlation_id),
    }
    assert json.loads(json.dumps(payload)) == payload
    assert set(payload) == {"execution_id", "attempt_number", "correlation_id"}


def test_recording_queue_rejects_invalid_attempt_number() -> None:
    with pytest.raises(ValueError, match="attempt"):
        RecordingJobQueue().publish(
            execution_id=uuid4(), attempt_number=0, correlation_id=uuid4()
        )


def test_rq_queue_uses_json_serializer_and_forwards_only_contract_payload() -> None:
    class FakeQueue:
        def __init__(self) -> None:
            self.calls: list[tuple[object, dict[str, object]]] = []

        def enqueue(self, name: object, **kwargs: object) -> object:
            self.calls.append((name, kwargs))
            return object()

    fake = FakeQueue()
    queue = RQJobQueue(fake, job_name="umbral.workers.worker.run_message")
    execution_id = uuid4()
    correlation_id = uuid4()

    queue.publish(
        execution_id=execution_id,
        attempt_number=2,
        correlation_id=correlation_id,
    )

    assert fake.calls[0][0] == "umbral.workers.worker.run_message"
    kwargs = fake.calls[0][1]
    assert kwargs["job_id"] == f"{execution_id}-2"
    assert kwargs["execution_id"] == str(execution_id)
    assert kwargs["attempt_number"] == 2
    assert kwargs["correlation_id"] == str(correlation_id)
    assert "pickle" not in repr(queue).lower()
