from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from tests.integration.jobs.conftest import JobRuntimeFactory

from umbral.application.jobs.relay import JobOutboxRelay
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue


def test_outbox_relay_rebuilds_transport_after_publish_interruption(
    job_runtime_factory: JobRuntimeFactory,
) -> None:
    queue = RecordingJobQueue()
    runtime = job_runtime_factory(queue)
    execution = runtime.submit_simple(
        "foundation.reference", "ref:outbox", str(uuid4())
    )
    queue.messages.clear()
    relay = JobOutboxRelay(runtime, queue)

    relay.publish_due(limit=10)
    relay.publish_due(limit=10)

    assert len(queue.messages) == 1
    assert queue.messages[0].payload["execution_id"] == str(execution.execution_id)


def test_outbox_relay_is_safe_when_redis_is_temporarily_unavailable(
    job_runtime_factory: JobRuntimeFactory,
) -> None:
    class FailingQueue(RecordingJobQueue):
        def publish(self, **kwargs: object) -> str:
            raise RuntimeError("redis unavailable")

    queue = FailingQueue()
    runtime = job_runtime_factory(queue)
    runtime.submit_simple("foundation.reference", "ref:outbox-2", str(uuid4()))
    relay = JobOutboxRelay(runtime, queue)

    result = relay.publish_due(limit=10)

    assert result.failed == 1
    assert runtime.pending_outbox_count() == 1


def test_rebuild_after_transport_loss_republishes_durable_rows(
    job_runtime_factory: JobRuntimeFactory,
) -> None:
    queue = RecordingJobQueue()
    runtime = job_runtime_factory(queue)
    runtime.submit_simple("foundation.reference", "ref:outbox-3", str(uuid4()))
    relay = JobOutboxRelay(runtime, queue)
    relay.publish_due(limit=10)
    queue.messages.clear()

    result = relay.rebuild_after_transport_loss(limit=10)

    assert result.published == 1
    assert len(queue.messages) == 1


def test_publish_failures_are_bounded_without_overflow(
    job_runtime_factory: JobRuntimeFactory,
) -> None:
    class CountingFailureQueue(RecordingJobQueue):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def publish(self, **kwargs: object) -> str:
            self.calls += 1
            raise RuntimeError("queue unavailable")

    queue = CountingFailureQueue()
    runtime = job_runtime_factory(queue)
    runtime.submit_simple("foundation.reference", "ref:bounded", str(uuid4()))

    for _ in range(100):
        assert runtime.relay_due(limit=1).failed == 1
        runtime.advance_time(timedelta(minutes=6))

    assert queue.calls == 100
    assert runtime.pending_outbox_count() == 0
    assert runtime.relay_due(limit=1).failed == 0
