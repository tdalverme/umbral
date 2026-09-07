from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from umbral.application.jobs.contracts import SubmitJob
from umbral.application.jobs.ports import RelayResult
from umbral.infrastructure.jobs import runtime as runtime_module
from umbral.infrastructure.jobs.runtime import SqlAlchemyJobRuntime
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


class _Session:
    def __init__(self) -> None:
        self.committed = False

    def __enter__(self) -> _Session:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        raise AssertionError("submit must not rollback after a committed relay")


class _Repository:
    def __init__(self, _session: _Session) -> None:
        pass

    def get_by_identity(self, _identity: object) -> None:
        return None

    def create_execution(self, command: SubmitJob, *, now: object) -> object:
        return SimpleNamespace(
            id=uuid4(),
            job_type=command.identity.job_type,
            logical_target=command.identity.logical_target,
            idempotency_key=command.identity.idempotency_key,
            state="pending",
            attempt_count=0,
            max_attempts=command.max_attempts,
            result_summary=None,
            error_code=None,
            available_at=now,
        )


def _command() -> SubmitJob:
    return SubmitJob.create(
        job_type="foundation.reference",
        logical_target="ref:immediate",
        idempotency_key="once",
        correlation_id=uuid4(),
    )


def test_submit_relays_new_outbox_after_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    monkeypatch.setattr(runtime_module, "SqlAlchemyJobRepository", _Repository)
    runtime = SqlAlchemyJobRuntime(
        cast(Callable[[], Session], lambda: session),
        queue=RecordingJobQueue(),
        now=lambda: NOW,
    )
    calls: list[tuple[bool, object | None]] = []

    def relay_due(
        *,
        limit: int,
        queue: object | None = None,
        execution_id: object | None = None,
    ) -> RelayResult:
        del queue
        calls.append((session.committed, execution_id))
        assert limit == 1
        return RelayResult(published=1)

    monkeypatch.setattr(runtime, "relay_due", relay_due)

    runtime.submit(_command())

    assert len(calls) == 1
    assert calls[0][0] is True
    assert isinstance(calls[0][1], UUID)


def test_submit_stays_successful_when_immediate_relay_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _Session()
    monkeypatch.setattr(runtime_module, "SqlAlchemyJobRepository", _Repository)
    runtime = SqlAlchemyJobRuntime(
        cast(Callable[[], Session], lambda: session),
        queue=RecordingJobQueue(),
        now=lambda: NOW,
    )
    calls: list[tuple[bool, object | None]] = []

    def relay_due(
        *,
        limit: int,
        queue: object | None = None,
        execution_id: object | None = None,
    ) -> RelayResult:
        del limit, queue
        calls.append((session.committed, execution_id))
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(runtime, "relay_due", relay_due)

    runtime.submit(_command())

    assert len(calls) == 1
    assert calls[0][0] is True
    assert isinstance(calls[0][1], UUID)
