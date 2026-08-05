from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from tests.integration.jobs.conftest import JobRuntimeFactory

from umbral.application.jobs.contracts import JobState, SubmitJob
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue


def _command(
    *, job_type: str = "foundation.reference", target: str = "ref:1", key: str = "same"
) -> SubmitJob:
    return SubmitJob.create(
        job_type=job_type,
        logical_target=target,
        idempotency_key=key,
        correlation_id=uuid4(),
    )


def test_ten_same_identity_submissions_return_one_execution(
    job_runtime_factory: JobRuntimeFactory,
) -> None:
    queue = RecordingJobQueue()
    runtime = job_runtime_factory(queue)
    command = _command()

    with ThreadPoolExecutor(max_workers=10) as pool:
        snapshots = list(pool.map(runtime.submit, [command] * 10))

    assert len({snapshot.execution_id for snapshot in snapshots}) == 1
    assert runtime.relay_due().published == 1
    assert len(queue.messages) == 1


def test_terminal_replay_publishes_nothing_and_new_key_reruns(
    job_runtime_factory: JobRuntimeFactory,
) -> None:
    queue = RecordingJobQueue()
    runtime = job_runtime_factory(queue)
    original = runtime.submit(_command())
    runtime.relay_due()
    runtime.complete(original.execution_id, {"ok": True})
    queue.messages.clear()

    replay = runtime.submit(_command())
    rerun = runtime.submit(_command(key="new-key"))
    runtime.relay_due()

    assert replay.state is JobState.SUCCEEDED
    assert replay.result == {"ok": True}
    assert replay.execution_id == original.execution_id
    assert rerun.execution_id != original.execution_id
    assert len(queue.messages) == 1


def test_same_key_different_type_or_target_is_independent(
    job_runtime_factory: JobRuntimeFactory,
) -> None:
    runtime = job_runtime_factory(RecordingJobQueue())
    first = runtime.submit(_command())
    second = runtime.submit(_command(job_type="other.job"))
    third = runtime.submit(_command(target="ref:2"))

    assert len({first.execution_id, second.execution_id, third.execution_id}) == 3
