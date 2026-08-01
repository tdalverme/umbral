"""Transactional PostgreSQL implementation of the durable job runtime."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import TypeGuard, cast
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from umbral.application.jobs.contracts import (
    AttemptState,
    FailureClassification,
    JobContext,
    JobIdentity,
    JobSnapshot,
    JobState,
    JsonScalar,
    SubmitJob,
    classify_failure,
)
from umbral.application.jobs.ports import JobClaim, JobQueue, RelayResult
from umbral.infrastructure.db.models.jobs import JobExecution, JobOutboxMessage
from umbral.infrastructure.db.repositories.jobs import SqlAlchemyJobRepository


class SqlAlchemyJobRuntime:
    """A session-per-operation runtime safe to share across worker processes."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        queue: JobQueue,
        now: Callable[[], datetime] | None = None,
        release_id: str = "foundation-local",
        lease_seconds: int = 60,
        outbox_lease_seconds: int = 30,
        handlers: Mapping[str, object] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self.queue = queue
        self._clock = now or (lambda: datetime.now(timezone.utc))
        self._offset = timedelta()
        self.release_id = release_id
        self.lease_seconds = lease_seconds
        self.outbox_lease_seconds = outbox_lease_seconds
        self.handlers = handlers

    @property
    def now(self) -> datetime:
        return _utc(self._clock()) + self._offset

    def advance_time(self, delta: timedelta) -> None:
        if delta.total_seconds() < 0:
            raise ValueError("time cannot move backwards")
        self._offset += delta

    def submit(self, command: SubmitJob) -> JobSnapshot:
        command = self._normalized_command(command)
        with self._session_factory() as session:
            repository = SqlAlchemyJobRepository(session)
            existing = repository.get_by_identity(command.identity)
            if existing is not None:
                return _snapshot(existing)
            try:
                execution = repository.create_execution(command, now=self.now)
                session.commit()
            except IntegrityError:
                session.rollback()
                winner = repository.get_by_identity(command.identity)
                if winner is None:
                    raise
                return _snapshot(winner)
            return _snapshot(execution)

    def submit_simple(
        self,
        job_type: str,
        logical_target: str,
        idempotency_key: str,
        *,
        max_attempts: int = 5,
    ) -> JobSnapshot:
        return self.submit(
            SubmitJob.create(
                job_type=job_type,
                logical_target=logical_target,
                idempotency_key=idempotency_key,
                max_attempts=max_attempts,
            )
        )

    def get(self, execution_id: UUID) -> JobSnapshot:
        with self._session_factory() as session:
            execution = SqlAlchemyJobRepository(session).get(execution_id)
            if execution is None:
                raise KeyError(execution_id)
            return _snapshot(execution)

    def identity(self, execution_id: UUID) -> JobIdentity:
        return self.get(execution_id).identity

    def correlation_id(self, execution_id: UUID) -> UUID:
        with self._session_factory() as session:
            execution = SqlAlchemyJobRepository(session).get(execution_id)
            if execution is None:
                raise KeyError(execution_id)
            return execution.correlation_id

    def claim(
        self, *, execution_id: UUID, attempt_number: int, worker_id: str
    ) -> JobClaim | None:
        with self._session_factory() as session:
            attempt = SqlAlchemyJobRepository(session).claim(
                execution_id,
                attempt_number,
                worker_id=worker_id,
                release_id=self.release_id,
                now=self.now,
                lease_seconds=self.lease_seconds,
            )
            if attempt is None:
                session.rollback()
                return None
            execution = session.get(JobExecution, execution_id)
            assert execution is not None
            claim = JobClaim(
                execution_id=execution_id,
                attempt_number=attempt_number,
                worker_id=worker_id,
                context=JobContext(
                    execution_id=execution_id,
                    attempt_number=attempt_number,
                    correlation_id=execution.correlation_id,
                    release_id=self.release_id,
                    logical_target=execution.logical_target,
                ),
            )
            session.commit()
            return claim

    def record_outcome(
        self, claim: JobClaim, outcome: Mapping[str, object] | Exception
    ) -> JobSnapshot:
        with self._session_factory() as session:
            repository = SqlAlchemyJobRepository(session)
            execution = repository.get_for_update(claim.execution_id)
            if execution is None:
                raise KeyError(claim.execution_id)
            attempt = repository.attempt_for_update(
                claim.execution_id, claim.attempt_number
            )
            if (
                attempt is None
                or execution.state != "running"
                or execution.attempt_count != claim.attempt_number
                or execution.lease_owner != claim.worker_id
                or execution.lease_until is None
                or execution.lease_until <= self.now
            ):
                session.rollback()
                return _snapshot(execution)

            timestamp = self.now
            if not isinstance(outcome, Exception):
                repository.finish_attempt(attempt, state="succeeded", now=timestamp)
                execution.result_summary = cast(
                    dict[str, object], _json_object(outcome)
                )
                execution.error_code = None
                execution.state = "succeeded"
                execution.finished_at = timestamp
            else:
                classification = classify_failure(outcome)
                repository.finish_attempt(
                    attempt,
                    state=_attempt_state(classification),
                    error_code=classification.code,
                    now=timestamp,
                )
                execution.error_code = classification.code
                if (
                    classification.kind == "transient"
                    and execution.attempt_count < execution.max_attempts
                ):
                    available_at = timestamp + timedelta(
                        seconds=_retry_delay(execution.attempt_count, outcome)
                    )
                    repository.schedule_retry(
                        execution,
                        available_at=available_at,
                        error_code=classification.code,
                        now=timestamp,
                    )
                else:
                    execution.state = "failed"
                    execution.finished_at = timestamp
            session.commit()
            return _snapshot(execution)

    def complete(self, execution_id: UUID, result: Mapping[str, object]) -> JobSnapshot:
        claim = self.claim(
            execution_id=execution_id,
            attempt_number=self.get(execution_id).attempt_count + 1,
            worker_id="manual",
        )
        if claim is None:
            return self.get(execution_id)
        return self.record_outcome(claim, result)

    def relay_due(
        self, *, limit: int = 100, queue: JobQueue | None = None
    ) -> RelayResult:
        limit = _limit(limit)
        target_queue = queue or self.queue
        owner = f"relay:{uuid4()}"
        with self._session_factory() as session:
            repository = SqlAlchemyJobRepository(session)
            repository.reclaim_expired_outbox(now=self.now, limit=limit)
            rows = repository.claim_outbox(
                owner=owner,
                now=self.now,
                lease_seconds=self.outbox_lease_seconds,
                limit=limit,
            )
            messages = [
                (row.id, row.execution_id, row.attempt_number) for row in rows
            ]
            correlations = {
                row.id: row.execution.correlation_id for row in rows
            }
            session.commit()

        published = failed = 0
        for message_id, execution_id, attempt_number in messages:
            try:
                target_queue.publish(
                    execution_id=execution_id,
                    attempt_number=attempt_number,
                    correlation_id=correlations[message_id],
                )
            except Exception:
                if self._finish_outbox(message_id, owner, published=False):
                    failed += 1
            else:
                if self._finish_outbox(message_id, owner, published=True):
                    published += 1
        return RelayResult(published=published, failed=failed)

    def rebuild_outbox(self, *, limit: int = 100) -> int:
        with self._session_factory() as session:
            rebuilt = SqlAlchemyJobRepository(session).rebuild_outbox(
                limit=_limit(limit)
            )
            session.commit()
            return rebuilt

    def pending_outbox_count(self) -> int:
        with self._session_factory() as session:
            from sqlalchemy import func, select

            return int(
                session.scalar(
                    select(func.count())
                    .select_from(JobOutboxMessage)
                    .where(JobOutboxMessage.state == "pending")
                )
                or 0
            )

    def reclaim_expired_outbox(self, *, limit: int = 100) -> int:
        with self._session_factory() as session:
            count = SqlAlchemyJobRepository(session).reclaim_expired_outbox(
                now=self.now, limit=_limit(limit)
            )
            session.commit()
            return count

    def reap_expired(self, *, limit: int = 100) -> int:
        with self._session_factory() as session:
            count = SqlAlchemyJobRepository(session).reap_expired(
                now=self.now, limit=_limit(limit)
            )
            session.commit()
            return count

    def add_schedule(
        self,
        *,
        job_type: str,
        logical_target: str,
        schedule_kind: str,
        next_run_at: datetime,
        interval_seconds: int | None = None,
        max_attempts: int = 5,
        schedule_id: UUID | None = None,
    ) -> UUID:
        if schedule_kind not in {"one_shot", "fixed_interval"}:
            raise ValueError("unsupported schedule kind")
        if schedule_kind == "fixed_interval" and (
            interval_seconds is None or interval_seconds < 60
        ):
            raise ValueError("fixed interval must be at least 60 seconds")
        with self._session_factory() as session:
            schedule = SqlAlchemyJobRepository(session).create_schedule(
                job_type=job_type,
                logical_target=logical_target,
                schedule_kind=schedule_kind,
                next_run_at=next_run_at,
                interval_seconds=interval_seconds,
                max_attempts=max_attempts,
                correlation_id=uuid4(),
                now=self.now,
            )
            if schedule_id is not None:
                schedule.id = schedule_id
            session.commit()
            return schedule.id

    def schedule_tick(self) -> int:
        with self._session_factory() as session:
            repository = SqlAlchemyJobRepository(session)
            schedule = repository.claim_due_schedule(now=self.now)
            if schedule is None:
                session.rollback()
                return 0
            planned = schedule.next_run_at
            command = SubmitJob.create(
                job_type=schedule.job_type,
                logical_target=schedule.logical_target,
                idempotency_key=f"schedule:{schedule.id}:{_canonical_utc(planned)}",
                correlation_id=schedule.correlation_id,
                max_attempts=schedule.max_attempts,
            )
            repository.create_execution(command, source="jobs.scheduler", now=self.now)
            repository.advance_schedule(schedule, now=self.now)
            session.commit()
            return 1

    def _finish_outbox(self, message_id: UUID, owner: str, *, published: bool) -> bool:
        with self._session_factory() as session:
            repository = SqlAlchemyJobRepository(session)
            row = repository.outbox_for_update(message_id)
            if (
                row is None
                or row.state != "publishing"
                or row.lease_owner != owner
                or row.lease_until is None
                or row.lease_until <= self.now
            ):
                session.rollback()
                return False
            if published:
                repository.mark_outbox_published(row, now=self.now)
            else:
                repository.mark_outbox_failed(row, now=self.now)
            session.commit()
            return True

    def _normalized_command(self, command: SubmitJob) -> SubmitJob:
        if self.handlers is None:
            return command
        handler = self.handlers.get(command.identity.job_type)
        if handler is None:
            raise ValueError(
                f"job handler is not registered: {command.identity.job_type}"
            )
        normalizer = getattr(handler, "normalize_target", None)
        if not callable(normalizer):
            return command
        target = normalizer(command.identity.logical_target)
        if target == command.identity.logical_target:
            return command
        return SubmitJob(
            identity=JobIdentity.create(
                command.identity.job_type, target, command.identity.idempotency_key
            ),
            correlation_id=command.correlation_id,
            actor=command.actor,
            max_attempts=command.max_attempts,
        )


def _snapshot(execution: JobExecution) -> JobSnapshot:
    return JobSnapshot(
        execution_id=execution.id,
        identity=JobIdentity.create(
            execution.job_type, execution.logical_target, execution.idempotency_key
        ),
        state=JobState(execution.state),
        attempt_count=execution.attempt_count,
        max_attempts=execution.max_attempts,
        result=cast(Mapping[str, JsonScalar] | None, execution.result_summary),
        error_code=execution.error_code,
        available_at=execution.available_at,
    )


def _retry_delay(attempt_count: int, outcome: Exception) -> int:
    retry_after: object = getattr(outcome, "retry_after", None)
    if isinstance(retry_after, timedelta):
        seconds: int = int(retry_after.total_seconds())
        return min(300, max(0, seconds))
    return min(300, 1 << max(0, attempt_count - 1))


def _attempt_state(classification: FailureClassification) -> str:
    if classification.kind == "transient":
        return AttemptState.TRANSIENT_FAILURE.value
    return AttemptState.PERMANENT_FAILURE.value


def _limit(value: int) -> int:
    if not 1 <= value <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _canonical_utc(value: datetime) -> str:
    return _utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_object(value: Mapping[str, object]) -> dict[str, JsonScalar]:
    result: dict[str, JsonScalar] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not _json_scalar(item):
            raise ValueError("job result must contain only JSON scalar values")
        result[key] = item
    encoded = json.dumps(result, separators=(",", ":"), ensure_ascii=False).encode()
    if len(encoded) > 8192:
        raise ValueError("job result exceeds the 8 KiB bound")
    return result


def _json_scalar(value: object) -> TypeGuard[JsonScalar]:
    return value is None or isinstance(value, (str, int, float, bool))
