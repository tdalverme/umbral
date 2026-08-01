"""PostgreSQL conformance checks for the durable SQLAlchemy job runtime."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tests.support.containers import ServiceConnection

from umbral.application.jobs.contracts import (
    JobSnapshot,
    JobState,
    SubmitJob,
    TransientJobError,
)
from umbral.infrastructure.db.repositories.jobs import SqlAlchemyJobRepository
from umbral.infrastructure.jobs.runtime import SqlAlchemyJobRuntime
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)
RuntimeFactory = Callable[..., SqlAlchemyJobRuntime]


@pytest.fixture
def runtime_factory(
    postgres_container: ServiceConnection,
) -> Iterator[RuntimeFactory]:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgres_container.url)
    command.upgrade(config, "head")
    engine = create_engine(postgres_container.url)
    factory = sessionmaker(engine, expire_on_commit=False)

    def create(*, queue: RecordingJobQueue | None = None) -> SqlAlchemyJobRuntime:
        return SqlAlchemyJobRuntime(
            factory,
            queue=queue or RecordingJobQueue(),
            now=lambda: NOW,
            release_id="test-release",
        )

    try:
        yield create
    finally:
        engine.dispose()


def _command(*, key: str = "same") -> SubmitJob:
    return SubmitJob.create(
        job_type="foundation.reference",
        logical_target="ref:sql",
        idempotency_key=key,
        correlation_id=uuid4(),
    )


def test_submit_is_atomic_and_idempotent_across_runtime_instances(
    runtime_factory: RuntimeFactory,
) -> None:
    queue = RecordingJobQueue()

    def submit_once(_: int) -> JobSnapshot:
        return runtime_factory(queue=queue).submit(_command())

    with ThreadPoolExecutor(max_workers=2) as executor:
        snapshots = list(executor.map(submit_once, range(2)))

    assert len({snapshot.execution_id for snapshot in snapshots}) == 1
    assert queue.messages == []
    assert runtime_factory(queue=queue).relay_due().published == 1
    assert len(queue.messages) == 1


def test_claim_outcome_retry_and_expired_lease_are_durable(
    runtime_factory: RuntimeFactory,
) -> None:
    runtime = runtime_factory()
    execution = runtime.submit(_command())
    assert runtime.relay_due().published == 1
    first = runtime.claim(
        execution_id=execution.execution_id, attempt_number=1, worker_id="one"
    )
    assert first is not None

    retried = runtime.record_outcome(first, TransientJobError("provider.timeout"))
    assert retried.state is JobState.RETRY_WAIT
    assert runtime.relay_due().published == 0
    later = runtime_factory()
    later.advance_time(timedelta(seconds=1))
    assert later.relay_due().published == 1
    second = later.claim(
        execution_id=execution.execution_id, attempt_number=2, worker_id="two"
    )
    assert second is not None
    later.advance_time(timedelta(seconds=61))
    assert later.reap_expired() == 1
    assert runtime_factory().get(execution.execution_id).state is JobState.RETRY_WAIT


def test_schedule_tick_locks_one_due_occurrence_across_instances(
    runtime_factory: RuntimeFactory,
) -> None:
    runtime = runtime_factory()
    runtime.add_schedule(
        job_type="foundation.reference",
        logical_target="ref:schedule",
        schedule_kind="one_shot",
        next_run_at=NOW,
    )
    barrier = Barrier(2)

    def tick(_: int) -> int:
        barrier.wait()
        return runtime_factory().schedule_tick()

    with ThreadPoolExecutor(max_workers=2) as executor:
        counts = list(executor.map(tick, range(2)))

    assert sum(counts) == 1


def test_expired_relay_owner_cannot_mark_and_a_new_relay_reclaims(
    runtime_factory: RuntimeFactory,
) -> None:
    class CountingQueue(RecordingJobQueue):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def publish(self, **kwargs: object) -> str:
            self.calls += 1
            return super().publish(**kwargs)  # type: ignore[arg-type]

    queue = CountingQueue()
    runtime = runtime_factory(queue=queue)
    execution = runtime.submit(_command())
    owner = "relay:crashed"
    with runtime._session_factory() as session:  # noqa: SLF001 - crash boundary setup
        row = SqlAlchemyJobRepository(session).claim_outbox(
            owner=owner, now=NOW, lease_seconds=30, limit=1
        )[0]
        message_id = row.id
        session.commit()

    runtime.advance_time(timedelta(seconds=31))
    assert not runtime._finish_outbox(message_id, owner, published=True)  # noqa: SLF001
    assert runtime.relay_due().published == 1
    assert queue.calls == 1
    assert runtime.get(execution.execution_id).state is JobState.QUEUED
