from __future__ import annotations

from uuid import uuid4

from umbral.application.jobs.relay import JobOutboxRelay
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue


def test_outbox_relay_rebuilds_transport_after_publish_interruption() -> None:
    queue = RecordingJobQueue()
    runtime = InMemoryJobRuntime(queue=queue)
    execution = runtime.submit_simple(
        "foundation.reference", "ref:outbox", str(uuid4())
    )
    queue.messages.clear()
    relay = JobOutboxRelay(runtime, queue)

    relay.publish_due(limit=10)
    relay.publish_due(limit=10)

    assert len(queue.messages) == 1
    assert queue.messages[0].payload["execution_id"] == str(execution.execution_id)


def test_outbox_relay_is_safe_when_redis_is_temporarily_unavailable() -> None:
    class FailingQueue(RecordingJobQueue):
        def publish(self, **kwargs: object) -> str:
            raise RuntimeError("redis unavailable")

    queue = FailingQueue()
    runtime = InMemoryJobRuntime(queue=queue)
    runtime.submit_simple("foundation.reference", "ref:outbox-2", str(uuid4()))
    relay = JobOutboxRelay(runtime, queue)

    result = relay.publish_due(limit=10)

    assert result.failed == 1
    assert runtime.pending_outbox_count() == 1


def test_rebuild_after_transport_loss_republishes_durable_rows() -> None:
    queue = RecordingJobQueue()
    runtime = InMemoryJobRuntime(queue=queue)
    runtime.submit_simple("foundation.reference", "ref:outbox-3", str(uuid4()))
    relay = JobOutboxRelay(runtime, queue)
    relay.publish_due(limit=10)
    queue.messages.clear()

    result = relay.rebuild_after_transport_loss(limit=10)

    assert result.published == 1
    assert len(queue.messages) == 1
