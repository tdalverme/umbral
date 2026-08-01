from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

from tests.integration.jobs.conftest import JobRuntimeFactory

from umbral.application.jobs.contracts import SubmitJob
from umbral.application.jobs.scheduler import InMemoryScheduler
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue


def test_two_schedulers_emit_one_utc_occurrence(
    job_runtime_factory: JobRuntimeFactory,
) -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    queue = RecordingJobQueue()
    runtime = job_runtime_factory(queue)
    schedule_id = runtime.add_schedule(
        job_type="foundation.reference",
        logical_target="ref:schedule",
        schedule_kind="one_shot",
        next_run_at=now - timedelta(seconds=1),
    )
    schedulers = [
        InMemoryScheduler(runtime, scheduler_id=f"s-{i}")
        for i in range(2)
    ]
    barrier = Barrier(2)

    def tick(scheduler: InMemoryScheduler) -> int:
        barrier.wait()
        return scheduler.tick()

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(tick, schedulers))

    assert sum(counts) == 1
    replay = runtime.submit(
        SubmitJob.create(
            job_type="foundation.reference",
            logical_target="ref:schedule",
            idempotency_key=(
                "schedule:"
                f"{schedule_id}:"
                f"{now.isoformat(timespec='seconds').replace('+00:00', 'Z')}"
            ),
        )
    )
    assert replay.identity.idempotency_key.startswith("schedule:")
    assert replay.identity.idempotency_key.endswith("Z")
