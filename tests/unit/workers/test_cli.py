from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from redis import Redis
from rq import Worker
from rq.serializers import JSONSerializer

import umbral.workers.__main__ as workers_cli
import umbral.workers.composition as worker_composition
from umbral.application.identity.ports import IdentityStore
from umbral.application.jobs.contracts import JobContext, JobState
from umbral.application.jobs.ports import JobQueue, JobRuntime
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.infrastructure.queue.rq_queue import RQJobQueue
from umbral.workers.__main__ import main
from umbral.workers.scheduler import scheduler_once
from umbral.workers.worker import InMemoryWorker, build_rq_worker, run_message


@dataclass
class _RetentionStore:
    events: list[str]

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.events.append("retention")
        yield

    def purge_requests_before(self, cutoff: object) -> int:
        del cutoff
        return 3


@dataclass
class _SchedulerRuntime:
    events: list[str] = field(default_factory=list)
    ticks: list[int] = field(default_factory=lambda: [1, 1, 0])

    def reclaim_expired_outbox(self, *, limit: int) -> int:
        self.events.append(f"reclaim:{limit}")
        return 2

    def reap_expired(self, *, limit: int) -> int:
        self.events.append(f"reap:{limit}")
        return 1

    def schedule_tick(self) -> int:
        self.events.append("schedule")
        return self.ticks.pop(0)

    def relay_due(self, *, queue: object, limit: int) -> object:
        del queue
        self.events.append(f"relay:{limit}")
        return SimpleNamespace(published=4, failed=0)


def test_rq_worker_uses_umbral_queue_and_json_serializer() -> None:
    connection = Redis.from_url("redis://127.0.0.1:6379/15")
    queue = RQJobQueue.from_connection(connection)

    worker = build_rq_worker(queue)

    assert isinstance(worker, Worker)
    assert worker.queues[0].name == "umbral"
    assert worker.serializer is JSONSerializer
    assert isinstance(worker.queues[0].serializer, JSONSerializer)


def test_run_message_claims_once_and_records_registered_handler_outcome() -> None:
    queue = RecordingJobQueue()
    runtime = InMemoryJobRuntime(queue=queue)
    execution = runtime.submit_simple("test.registered", "target", "message-1")
    calls: list[UUID] = []

    def handler(context: JobContext) -> Mapping[str, bool]:
        calls.append(context.execution_id)
        return {"processed": True}

    worker = InMemoryWorker(runtime, {"test.registered": handler}, worker_id="test")

    assert run_message(
        execution_id=str(execution.execution_id),
        attempt_number=1,
        correlation_id=str(runtime.correlation_id(execution.execution_id)),
        worker=worker,
    )
    assert calls == [execution.execution_id]
    assert runtime.get(execution.execution_id).state is JobState.SUCCEEDED
    assert not run_message(
        execution_id=str(execution.execution_id),
        attempt_number=1,
        correlation_id=str(runtime.correlation_id(execution.execution_id)),
        worker=worker,
    )


def test_run_message_rejects_invalid_or_mismatched_identity_before_claim() -> None:
    queue = RecordingJobQueue()
    runtime = InMemoryJobRuntime(queue=queue)
    execution = runtime.submit_simple("test.unregistered", "target", "message-2")
    worker = InMemoryWorker(runtime, {}, worker_id="test")

    try:
        run_message(
            execution_id="not-a-uuid",
            attempt_number=1,
            correlation_id=str(uuid4()),
            worker=worker,
        )
    except ValueError:
        pass
    else:
        raise AssertionError("invalid envelope must fail validation")
    assert not run_message(
        execution_id=str(execution.execution_id),
        attempt_number=1,
        correlation_id=str(uuid4()),
        worker=worker,
    )
    assert runtime.get(execution.execution_id).attempt_count == 0


def test_run_message_records_an_unregistered_handler_as_a_stable_failure() -> None:
    queue = RecordingJobQueue()
    runtime = InMemoryJobRuntime(queue=queue)
    execution = runtime.submit_simple("test.unregistered", "target", "message-3")
    worker = InMemoryWorker(runtime, {}, worker_id="test")

    assert run_message(
        execution_id=str(execution.execution_id),
        attempt_number=1,
        correlation_id=str(runtime.correlation_id(execution.execution_id)),
        worker=worker,
    )

    snapshot = runtime.get(execution.execution_id)
    assert snapshot.state is JobState.FAILED
    assert snapshot.error_code == "job.handler_not_registered"


def test_run_message_rebuilds_child_composition_for_each_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queue = RecordingJobQueue()
    runtime = InMemoryJobRuntime(queue=queue)
    first = runtime.submit_simple("test.registered", "first", "message-4")
    second = runtime.submit_simple("test.registered", "second", "message-5")
    effects: list[UUID] = []
    compositions = 0

    def handler(context: JobContext) -> Mapping[str, bool]:
        effects.append(context.execution_id)
        return {"processed": True}

    def compose() -> object:
        nonlocal compositions
        compositions += 1
        return SimpleNamespace(
            runtime=runtime,
            handlers={"test.registered": handler},
            worker_id=f"child-{compositions}",
        )

    monkeypatch.setattr(worker_composition, "build_process_dependencies", compose)

    for execution in (first, second):
        assert run_message(
            execution_id=str(execution.execution_id),
            attempt_number=1,
            correlation_id=str(runtime.correlation_id(execution.execution_id)),
        )

    assert compositions == 2
    assert effects == [first.execution_id, second.execution_id]
    assert runtime.get(first.execution_id).state is JobState.SUCCEEDED
    assert runtime.get(second.execution_id).state is JobState.SUCCEEDED


def test_scheduler_once_runs_durable_steps_in_order_and_returns_summary() -> None:
    runtime = _SchedulerRuntime()
    store = _RetentionStore(runtime.events)

    result = scheduler_once(
        cast(JobRuntime, runtime),
        queue=cast(JobQueue, object()),
        identity_store=cast(IdentityStore, store),
        limit=7,
    )

    assert result == {
        "reclaimed_outbox": 2,
        "reaped_jobs": 1,
        "scheduled": 2,
        "published": 4,
        "failed": 0,
        "purged_requests": 3,
    }
    assert runtime.events == [
        "reclaim:7",
        "reap:7",
        "schedule",
        "schedule",
        "schedule",
        "relay:7",
        "retention",
    ]


def test_scheduler_once_emits_a_bounded_summary(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = _SchedulerRuntime()
    dependencies = SimpleNamespace(
        settings=SimpleNamespace(environment="local"),
        runtime=runtime,
        queue=object(),
        identity_store=_RetentionStore(runtime.events),
    )

    shutdowns: list[None] = []
    monkeypatch.setattr(
        workers_cli,
        "shutdown_observability",
        lambda: shutdowns.append(None),
        raising=False,
    )

    assert main(["scheduler-once"], dependencies=dependencies) == 0
    assert capsys.readouterr().out == (
        '{"failed":0,"published":4,"purged_requests":3,"reaped_jobs":1,'
        '"reclaimed_outbox":2,"scheduled":2}\n'
    )
    assert shutdowns == [None]


def test_scheduler_once_exits_nonzero_without_exposing_dependency_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class FailingRuntime(_SchedulerRuntime):
        def reclaim_expired_outbox(self, *, limit: int) -> int:
            del limit
            raise RuntimeError("redis://secret@host")

    dependencies = SimpleNamespace(
        settings=SimpleNamespace(environment="local"),
        runtime=FailingRuntime(),
        queue=object(),
        identity_store=_RetentionStore([]),
    )

    assert main(["scheduler-once"], dependencies=dependencies) == 1
    captured = capsys.readouterr()
    assert "redis://secret@host" not in captured.err


def test_scheduler_is_rejected_in_preview() -> None:
    dependencies = SimpleNamespace(settings=SimpleNamespace(environment="preview"))

    assert main(["scheduler"], dependencies=dependencies) == 2


@pytest.mark.parametrize("worker_result", [True, False])
def test_worker_normal_completion_always_exits_zero(
    monkeypatch: pytest.MonkeyPatch, worker_result: bool
) -> None:
    dependencies = SimpleNamespace(
        settings=SimpleNamespace(environment="local"), queue=object()
    )
    monkeypatch.setattr(
        workers_cli,
        "build_rq_worker",
        lambda queue: SimpleNamespace(work=lambda: worker_result),
    )

    assert main(["worker"], dependencies=dependencies) == 0


def test_worker_exception_exits_nonzero_without_exposing_dependency_value(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dependencies = SimpleNamespace(
        settings=SimpleNamespace(environment="local"), queue=object()
    )

    def fail_worker(queue: object) -> object:
        del queue
        raise RuntimeError("redis://canary-secret@host")

    monkeypatch.setattr(workers_cli, "build_rq_worker", fail_worker)

    assert main(["worker"], dependencies=dependencies) == 1
    captured = capsys.readouterr()
    assert captured.err == "worker failed\n"
    assert "canary-secret" not in captured.out + captured.err


@pytest.mark.parametrize("command", ["worker", "scheduler-once"])
def test_composition_failure_is_a_safe_nonzero_process_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    def fail_composition() -> object:
        raise RuntimeError("postgresql://canary-secret@host")

    monkeypatch.setattr(
        worker_composition, "build_process_dependencies", fail_composition
    )

    assert main([command]) == 1
    captured = capsys.readouterr()
    assert captured.err == f"{command} failed\n"
    assert "canary-secret" not in captured.out + captured.err
