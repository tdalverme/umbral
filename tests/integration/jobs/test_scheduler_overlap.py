from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

from umbral.application.jobs.scheduler import InMemoryScheduler
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue


def test_two_schedulers_emit_one_utc_occurrence() -> None:
    now = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
    queue = RecordingJobQueue()
    runtime = InMemoryJobRuntime(queue=queue, now=now)
    runtime.add_schedule(
        job_type="foundation.reference",
        logical_target="ref:schedule",
        schedule_kind="one_shot",
        next_run_at=now - timedelta(seconds=1),
    )
    schedulers = [InMemoryScheduler(runtime, scheduler_id=f"s-{i}") for i in range(2)]
    barrier = Barrier(2)

    def tick(scheduler: InMemoryScheduler) -> int:
        barrier.wait()
        return scheduler.tick()

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(tick, schedulers))

    assert sum(counts) == 1
    assert len(runtime.submissions) == 1
    assert runtime.submissions[0].identity.idempotency_key.startswith("schedule:")
    assert runtime.submissions[0].identity.idempotency_key.endswith("Z")
