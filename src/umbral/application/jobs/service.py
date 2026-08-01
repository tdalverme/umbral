"""Minimal durable-job runtime used by tests and local development.

The production seam is deliberately repository/transaction based.  This
adapter keeps the same identity, lease and outbox rules in memory so the
application contracts can be exercised without a live PostgreSQL/Redis pair.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import TypeGuard
from uuid import UUID, uuid4

from .contracts import (
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
from .ports import JobClaim, JobQueue, RelayResult


@dataclass(slots=True)
class _Attempt:
    ordinal: int
    worker_id: str
    started_at: datetime
    state: AttemptState = AttemptState.RUNNING
    finished_at: datetime | None = None
    error_code: str | None = None


@dataclass(slots=True)
class _Outbox:
    execution_id: UUID
    attempt_number: int
    available_at: datetime
    state: str = "pending"
    publish_attempts: int = 0
    error_code: str | None = None


@dataclass(slots=True)
class _Execution:
    execution_id: UUID
    identity: JobIdentity
    correlation_id: UUID
    max_attempts: int
    created_at: datetime
    available_at: datetime
    state: JobState = JobState.PENDING
    attempt_count: int = 0
    result: dict[str, JsonScalar] | None = None
    error_code: str | None = None
    finished_at: datetime | None = None
    lease_owner: str | None = None
    lease_until: datetime | None = None
    attempts: list[_Attempt] = field(default_factory=list)


@dataclass(slots=True)
class _Schedule:
    schedule_id: UUID
    job_type: str
    logical_target: str
    schedule_kind: str
    next_run_at: datetime
    interval_seconds: int | None
    max_attempts: int
    enabled: bool = True
    last_scheduled_at: datetime | None = None


class InMemoryJobRuntime:
    """Thread-safe reference runtime implementing the durable job rules."""

    def __init__(
        self,
        *,
        queue: JobQueue,
        now: datetime | None = None,
        release_id: str = "foundation-local",
        lease_seconds: int = 60,
        handlers: Mapping[str, object] | None = None,
    ) -> None:
        self.queue = queue
        self.release_id = release_id
        self.lease_seconds = lease_seconds
        self.handlers = handlers
        self._now = _utc(now or datetime.now(timezone.utc))
        self._lock = RLock()
        self._executions: dict[UUID, _Execution] = {}
        self._identity_index: dict[tuple[str, str, str], UUID] = {}
        self._outbox: dict[tuple[UUID, int], _Outbox] = {}
        self._schedules: dict[UUID, _Schedule] = {}
        self.submissions: list[JobSnapshot] = []

    @property
    def now(self) -> datetime:
        with self._lock:
            return self._now

    def advance_time(self, delta: timedelta) -> None:
        if delta.total_seconds() < 0:
            raise ValueError("time cannot move backwards")
        with self._lock:
            self._now += delta

    def submit(self, command: SubmitJob) -> JobSnapshot:
        with self._lock:
            if self.handlers is not None:
                handler = self.handlers.get(command.identity.job_type)
                if handler is None:
                    raise ValueError(
                        f"job handler is not registered: {command.identity.job_type}"
                    )
                normalizer = getattr(handler, "normalize_target", None)
                if callable(normalizer):
                    normalized_target = normalizer(command.identity.logical_target)
                    if normalized_target != command.identity.logical_target:
                        command = SubmitJob(
                            identity=JobIdentity.create(
                                command.identity.job_type,
                                normalized_target,
                                command.identity.idempotency_key,
                            ),
                            correlation_id=command.correlation_id,
                            actor=command.actor,
                            max_attempts=command.max_attempts,
                        )
            existing_id = self._identity_index.get(command.identity.key)
            if existing_id is not None:
                return self._snapshot(self._executions[existing_id])

            execution = _Execution(
                execution_id=uuid4(),
                identity=command.identity,
                correlation_id=command.correlation_id,
                max_attempts=command.max_attempts,
                created_at=self._now,
                available_at=self._now,
            )
            self._executions[execution.execution_id] = execution
            self._identity_index[command.identity.key] = execution.execution_id
            self._outbox[(execution.execution_id, 1)] = _Outbox(
                execution_id=execution.execution_id,
                attempt_number=1,
                available_at=self._now,
            )
            snapshot = self._snapshot(execution)
            self.submissions.append(snapshot)
            return snapshot

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
        with self._lock:
            execution = self._executions.get(execution_id)
            if execution is None:
                raise KeyError(execution_id)
            return self._snapshot(execution)

    def identity(self, execution_id: UUID) -> JobIdentity:
        with self._lock:
            return self._executions[execution_id].identity

    def correlation_id(self, execution_id: UUID) -> UUID:
        with self._lock:
            return self._executions[execution_id].correlation_id

    def claim(
        self,
        *,
        execution_id: UUID,
        attempt_number: int,
        worker_id: str,
    ) -> JobClaim | None:
        with self._lock:
            execution = self._executions.get(execution_id)
            if execution is None or attempt_number != execution.attempt_count + 1:
                return None
            if execution.state in (JobState.SUCCEEDED, JobState.FAILED):
                return None
            if (
                execution.state is JobState.RETRY_WAIT
                and execution.available_at > self._now
            ):
                return None
            if execution.state is JobState.RUNNING:
                if execution.lease_until is None or execution.lease_until > self._now:
                    return None
                self._abandon_locked(execution)
                return None
            if execution.available_at > self._now:
                return None
            execution.attempt_count += 1
            execution.state = JobState.RUNNING
            execution.lease_owner = worker_id
            execution.lease_until = self._now + timedelta(seconds=self.lease_seconds)
            attempt = _Attempt(
                ordinal=attempt_number,
                worker_id=worker_id,
                started_at=self._now,
            )
            execution.attempts.append(attempt)
            return JobClaim(
                execution_id=execution_id,
                attempt_number=attempt_number,
                worker_id=worker_id,
                context=JobContext(
                    execution_id=execution_id,
                    attempt_number=attempt_number,
                    correlation_id=execution.correlation_id,
                    release_id=self.release_id,
                    logical_target=execution.identity.logical_target,
                ),
            )

    def record_outcome(
        self,
        claim: JobClaim,
        outcome: Mapping[str, object] | Exception,
    ) -> JobSnapshot:
        with self._lock:
            execution = self._executions[claim.execution_id]
            if (
                execution.state is not JobState.RUNNING
                or execution.attempt_count != claim.attempt_number
                or execution.lease_owner != claim.worker_id
                or execution.lease_until is None
                or execution.lease_until <= self._now
            ):
                return self._snapshot(execution)
            attempt = execution.attempts[-1]
            attempt.finished_at = self._now
            execution.lease_owner = None
            execution.lease_until = None
            if not isinstance(outcome, Exception):
                execution.result = _json_object(outcome)
                execution.error_code = None
                execution.state = JobState.SUCCEEDED
                execution.finished_at = self._now
                attempt.state = AttemptState.SUCCEEDED
                return self._snapshot(execution)

            classification = classify_failure(outcome)
            attempt.error_code = classification.code
            attempt.state = _attempt_state(classification)
            execution.error_code = classification.code
            if (
                classification.kind == "transient"
                and execution.attempt_count < execution.max_attempts
            ):
                execution.state = JobState.RETRY_WAIT
                delay = min(300, 2 ** max(0, execution.attempt_count - 1))
                if (
                    hasattr(outcome, "retry_after")
                    and getattr(outcome, "retry_after") is not None
                ):
                    delay = min(
                        300,
                        max(0, int(getattr(outcome, "retry_after").total_seconds())),
                    )
                execution.available_at = self._now + timedelta(seconds=delay)
                self._outbox[
                    (execution.execution_id, execution.attempt_count + 1)
                ] = _Outbox(
                    execution_id=execution.execution_id,
                    attempt_number=execution.attempt_count + 1,
                    available_at=execution.available_at,
                )
            else:
                execution.state = JobState.FAILED
                execution.finished_at = self._now
            return self._snapshot(execution)

    def complete(self, execution_id: UUID, result: Mapping[str, object]) -> JobSnapshot:
        with self._lock:
            execution = self._executions[execution_id]
            execution.result = _json_object(result)
            execution.state = JobState.SUCCEEDED
            execution.finished_at = self._now
            execution.lease_owner = None
            execution.lease_until = None
            return self._snapshot(execution)

    def relay_due(
        self, *, queue: JobQueue | None = None, limit: int = 100
    ) -> RelayResult:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        target_queue = queue or self.queue
        published = 0
        failed = 0
        with self._lock:
            due = [
                outbox
                for outbox in self._outbox.values()
                if (
                    outbox.state == "pending"
                    and outbox.available_at <= self._now
                    and outbox.publish_attempts < 100
                )
            ][:limit]
            for outbox in due:
                execution = self._executions[outbox.execution_id]
                try:
                    target_queue.publish(
                        execution_id=execution.execution_id,
                        attempt_number=outbox.attempt_number,
                        correlation_id=execution.correlation_id,
                    )
                except Exception:
                    outbox.publish_attempts += 1
                    outbox.error_code = "queue.publish_failed"
                    if outbox.publish_attempts >= 100:
                        outbox.state = "failed"
                    else:
                        outbox.available_at = self._now + timedelta(
                            seconds=min(300, 1 << max(0, outbox.publish_attempts - 1))
                        )
                    failed += 1
                else:
                    outbox.state = "published"
                    execution.state = (
                        JobState.QUEUED
                        if outbox.attempt_number == execution.attempt_count + 1
                        else execution.state
                    )
                    published += 1
        return RelayResult(published=published, failed=failed)

    def pending_outbox_count(self) -> int:
        with self._lock:
            return sum(row.state == "pending" for row in self._outbox.values())

    def rebuild_outbox(self, *, limit: int = 100) -> int:
        """Mark transport rows publishable after Redis state is lost."""

        with self._lock:
            rebuilt = 0
            for row in list(self._outbox.values())[:limit]:
                if row.state == "published":
                    row.state = "pending"
                    row.error_code = None
                    rebuilt += 1
            return rebuilt

    def reap_expired(self, *, limit: int = 100) -> int:
        with self._lock:
            count = 0
            for execution in list(self._executions.values())[:limit]:
                if (
                    execution.state is JobState.RUNNING
                    and execution.lease_until is not None
                    and execution.lease_until <= self._now
                ):
                    self._abandon_locked(execution)
                    count += 1
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
        with self._lock:
            identifier = schedule_id or uuid4()
            self._schedules[identifier] = _Schedule(
                schedule_id=identifier,
                job_type=job_type,
                logical_target=logical_target,
                schedule_kind=schedule_kind,
                next_run_at=_utc(next_run_at),
                interval_seconds=interval_seconds,
                max_attempts=max_attempts,
            )
            return identifier

    def schedule_tick(self) -> int:
        with self._lock:
            for schedule in self._schedules.values():
                if not schedule.enabled or schedule.next_run_at > self._now:
                    continue
                planned = schedule.next_run_at
                key = f"schedule:{schedule.schedule_id}:{_canonical_utc(planned)}"
                command = SubmitJob.create(
                    job_type=schedule.job_type,
                    logical_target=schedule.logical_target,
                    idempotency_key=key,
                    max_attempts=schedule.max_attempts,
                )
                self.submit(command)
                schedule.last_scheduled_at = planned
                if schedule.schedule_kind == "one_shot":
                    schedule.enabled = False
                else:
                    assert schedule.interval_seconds is not None
                    schedule.next_run_at = planned + timedelta(
                        seconds=schedule.interval_seconds
                    )
                return 1
            return 0

    def _abandon_locked(self, execution: _Execution) -> None:
        if execution.attempts:
            attempt = execution.attempts[-1]
            attempt.state = AttemptState.ABANDONED
            attempt.finished_at = self._now
            attempt.error_code = "job.lease_expired"
        execution.lease_owner = None
        execution.lease_until = None
        execution.error_code = "job.lease_expired"
        if execution.attempt_count < execution.max_attempts:
            execution.state = JobState.RETRY_WAIT
            execution.available_at = self._now
            self._outbox[
                (execution.execution_id, execution.attempt_count + 1)
            ] = _Outbox(
                execution_id=execution.execution_id,
                attempt_number=execution.attempt_count + 1,
                available_at=self._now,
            )
        else:
            execution.state = JobState.FAILED
            execution.finished_at = self._now

    @staticmethod
    def _snapshot(execution: _Execution) -> JobSnapshot:
        return JobSnapshot(
            execution_id=execution.execution_id,
            identity=execution.identity,
            state=execution.state,
            attempt_count=execution.attempt_count,
            max_attempts=execution.max_attempts,
            result=execution.result,
            error_code=execution.error_code,
            available_at=execution.available_at,
        )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _canonical_utc(value: datetime) -> str:
    return _utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _attempt_state(classification: FailureClassification) -> AttemptState:
    if classification.kind == "transient":
        return AttemptState.TRANSIENT_FAILURE
    return AttemptState.PERMANENT_FAILURE


def _json_object(value: Mapping[str, object]) -> dict[str, JsonScalar]:
    if not isinstance(value, Mapping):
        raise TypeError("job result must be a JSON object")
    output: dict[str, JsonScalar] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not _json_scalar(item):
            raise ValueError("job result must contain only JSON scalar values")
        output[key] = item
    serialized = json.dumps(
        output, separators=(",", ":"), ensure_ascii=False
    ).encode()
    if len(serialized) > 8192:
        raise ValueError("job result exceeds the 8 KiB bound")
    return output


def _json_scalar(value: object) -> TypeGuard[JsonScalar]:
    return value is None or isinstance(value, (str, int, float, bool))


# Names used by composition code can refer to the reference implementation
# without coupling callers to its storage strategy.
JobService = InMemoryJobRuntime
DurableJobRuntime = InMemoryJobRuntime
