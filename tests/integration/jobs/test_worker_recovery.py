from __future__ import annotations

from datetime import timedelta
from typing import cast
from uuid import uuid4

from tests.integration.jobs.conftest import JobRuntimeFactory

from umbral.application.jobs.contracts import JobContext, JobState, TransientJobError
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.workers.worker import InMemoryWorker


def test_duplicate_delivery_and_effect_before_ack_do_not_duplicate_effect(
    job_runtime_factory: JobRuntimeFactory,
) -> None:
    queue = RecordingJobQueue()
    runtime = job_runtime_factory(queue)
    effects: list[str] = []

    def handler(context: JobContext) -> dict[str, bool]:
        if context.execution_id.hex not in effects:
            effects.append(context.execution_id.hex)
        return {"ok": True}

    execution = runtime.submit_simple("foundation.reference", "ref:1", str(uuid4()))
    runtime.relay_due()
    worker = InMemoryWorker(
        cast(InMemoryJobRuntime, runtime),
        {"foundation.reference": handler},
        worker_id="w1",
    )
    message = queue.messages[0]

    worker.process(message)
    worker.process(message)

    assert effects == [execution.execution_id.hex]
    assert runtime.get(execution.execution_id).state is JobState.SUCCEEDED


def test_transient_failure_is_bounded_and_lease_can_be_reaped(
    job_runtime_factory: JobRuntimeFactory,
) -> None:
    queue = RecordingJobQueue()
    runtime = job_runtime_factory(queue)
    calls = 0

    def handler(context: JobContext) -> dict[str, bool]:
        nonlocal calls
        calls += 1
        if calls < 5:
            raise TransientJobError("provider.timeout")
        return {"ok": True}

    execution = runtime.submit_simple("foundation.reference", "ref:2", str(uuid4()))
    runtime.relay_due()
    worker = InMemoryWorker(
        cast(InMemoryJobRuntime, runtime),
        {"foundation.reference": handler},
        worker_id="w1",
    )

    for _ in range(4):
        worker.process(queue.messages[-1])
        runtime.advance_time(timedelta(hours=1))
        runtime.relay_due()
    worker.process(queue.messages[-1])

    assert calls == 5
    assert runtime.get(execution.execution_id).state is JobState.SUCCEEDED
