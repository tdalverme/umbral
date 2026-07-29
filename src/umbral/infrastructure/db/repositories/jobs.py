"""Specific job persistence operations; transaction ownership stays external."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from umbral.application.jobs.contracts import JobIdentity, SubmitJob
from umbral.infrastructure.db.models.jobs import (
    JobAttempt,
    JobExecution,
    JobOutboxMessage,
    JobSchedule,
)


class SqlAlchemyJobRepository:
    """Repository for execution/attempt/outbox/schedule lock operations.

    Methods flush changes but never commit.  Callers compose these operations
    with the application transaction manager so effect, result and outbox
    updates remain atomic.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, execution_id: UUID) -> JobExecution | None:
        return self.session.get(JobExecution, execution_id)

    def get_by_identity(self, identity: JobIdentity) -> JobExecution | None:
        return self.session.scalar(
            select(JobExecution).where(
                JobExecution.job_type == identity.job_type,
                JobExecution.logical_target == identity.logical_target,
                JobExecution.idempotency_key == identity.idempotency_key,
            )
        )

    def create_execution(
        self,
        command: SubmitJob,
        *,
        source: str = "jobs.submit",
        now: datetime | None = None,
    ) -> JobExecution:
        timestamp = _utc(now or datetime.now(timezone.utc))
        execution = JobExecution(
            id=uuid4(),
            created_at=timestamp,
            updated_at=timestamp,
            actor_kind=command.actor.kind,
            actor_id=command.actor.id,
            source=source,
            correlation_id=command.correlation_id,
            job_type=command.identity.job_type,
            logical_target=command.identity.logical_target,
            idempotency_key=command.identity.idempotency_key,
            state="pending",
            attempt_count=0,
            max_attempts=command.max_attempts,
            available_at=timestamp,
        )
        outbox = JobOutboxMessage(
            id=uuid4(),
            execution_id=execution.id,
            attempt_number=1,
            state="pending",
            available_at=timestamp,
            publish_attempts=0,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.session.add_all([execution, outbox])
        self.session.flush()
        return execution

    def claim(
        self,
        execution_id: UUID,
        attempt_number: int,
        *,
        worker_id: str,
        release_id: str,
        now: datetime | None = None,
        lease_seconds: int = 60,
    ) -> JobAttempt | None:
        timestamp = _utc(now or datetime.now(timezone.utc))
        execution = self.session.scalar(
            select(JobExecution)
            .where(JobExecution.id == execution_id)
            .with_for_update(skip_locked=True)
        )
        if execution is None or attempt_number != execution.attempt_count + 1:
            return None
        if execution.state in {"succeeded", "failed"}:
            return None
        if execution.state == "retry_wait" and execution.available_at > timestamp:
            return None
        if execution.state == "running":
            if execution.lease_until is None or execution.lease_until > timestamp:
                return None
            self.abandon(execution, now=timestamp)
            return None
        if execution.available_at > timestamp:
            return None

        execution.attempt_count = attempt_number
        execution.state = "running"
        execution.lease_owner = worker_id
        execution.lease_until = timestamp + timedelta(seconds=lease_seconds)
        execution.updated_at = timestamp
        attempt = JobAttempt(
            id=uuid4(),
            execution_id=execution.id,
            ordinal=attempt_number,
            transport_message_id=f"{execution.id}:{attempt_number}",
            worker_id=worker_id,
            state="running",
            started_at=timestamp,
            correlation_id=execution.correlation_id,
            release_id=release_id,
        )
        self.session.add(attempt)
        self.session.flush()
        return attempt

    def finish_attempt(
        self,
        attempt: JobAttempt,
        *,
        state: str,
        now: datetime | None = None,
        error_code: str | None = None,
    ) -> JobExecution:
        timestamp = _utc(now or datetime.now(timezone.utc))
        execution = self.session.get(JobExecution, attempt.execution_id)
        if execution is None:
            raise KeyError(attempt.execution_id)
        attempt.state = state
        attempt.finished_at = timestamp
        attempt.duration_ms = max(
            0, int((timestamp - attempt.started_at).total_seconds() * 1000)
        )
        attempt.error_code = error_code
        execution.lease_owner = None
        execution.lease_until = None
        execution.updated_at = timestamp
        self.session.flush()
        return execution

    def schedule_retry(
        self,
        execution: JobExecution,
        *,
        available_at: datetime,
        error_code: str,
        now: datetime | None = None,
    ) -> JobOutboxMessage:
        timestamp = _utc(now or datetime.now(timezone.utc))
        next_attempt = execution.attempt_count + 1
        execution.state = "retry_wait"
        execution.available_at = _utc(available_at)
        execution.error_code = error_code
        execution.updated_at = timestamp
        outbox = JobOutboxMessage(
            id=uuid4(),
            execution_id=execution.id,
            attempt_number=next_attempt,
            state="pending",
            available_at=_utc(available_at),
            publish_attempts=0,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.session.add(outbox)
        self.session.flush()
        return outbox

    def create_outbox(
        self,
        execution: JobExecution,
        *,
        attempt_number: int,
        available_at: datetime,
        now: datetime | None = None,
    ) -> JobOutboxMessage:
        timestamp = _utc(now or datetime.now(timezone.utc))
        outbox = JobOutboxMessage(
            id=uuid4(),
            execution_id=execution.id,
            attempt_number=attempt_number,
            state="pending",
            available_at=_utc(available_at),
            publish_attempts=0,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.session.add(outbox)
        self.session.flush()
        return outbox

    def claim_outbox(
        self,
        *,
        owner: str,
        now: datetime | None = None,
        lease_seconds: int = 30,
        limit: int = 100,
    ) -> list[JobOutboxMessage]:
        timestamp = _utc(now or datetime.now(timezone.utc))
        rows = list(
            self.session.scalars(
                select(JobOutboxMessage)
                .where(
                    JobOutboxMessage.state == "pending",
                    JobOutboxMessage.available_at <= timestamp,
                )
                .order_by(JobOutboxMessage.available_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.state = "publishing"
            row.lease_owner = owner
            row.lease_until = timestamp + timedelta(seconds=lease_seconds)
            row.publish_attempts += 1
            row.updated_at = timestamp
        self.session.flush()
        return rows

    def mark_outbox_published(
        self, row: JobOutboxMessage, *, now: datetime | None = None
    ) -> None:
        timestamp = _utc(now or datetime.now(timezone.utc))
        row.state = "published"
        row.published_at = timestamp
        row.lease_owner = None
        row.lease_until = None
        row.updated_at = timestamp
        execution = self.session.get(JobExecution, row.execution_id)
        if execution is not None and execution.state == "pending":
            execution.state = "queued"
            execution.updated_at = timestamp
        self.session.flush()

    def mark_outbox_failed(
        self,
        row: JobOutboxMessage,
        *,
        error_code: str = "queue.publish_failed",
        now: datetime | None = None,
    ) -> None:
        timestamp = _utc(now or datetime.now(timezone.utc))
        row.state = "pending"
        row.error_code = error_code
        row.lease_owner = None
        row.lease_until = None
        row.updated_at = timestamp
        self.session.flush()

    def reclaim_expired_outbox(
        self, *, now: datetime | None = None, limit: int = 100
    ) -> int:
        timestamp = _utc(now or datetime.now(timezone.utc))
        rows = list(
            self.session.scalars(
                select(JobOutboxMessage)
                .where(
                    JobOutboxMessage.state == "publishing",
                    JobOutboxMessage.lease_until <= timestamp,
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.state = "pending"
            row.lease_owner = None
            row.lease_until = None
            row.updated_at = timestamp
        self.session.flush()
        return len(rows)

    def reap_expired(
        self, *, now: datetime | None = None, limit: int = 100
    ) -> int:
        timestamp = _utc(now or datetime.now(timezone.utc))
        executions = list(
            self.session.scalars(
                select(JobExecution)
                .where(
                    JobExecution.state == "running",
                    JobExecution.lease_until <= timestamp,
                )
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for execution in executions:
            self.abandon(execution, now=timestamp)
        return len(executions)

    def create_schedule(
        self,
        *,
        job_type: str,
        logical_target: str,
        schedule_kind: str,
        next_run_at: datetime,
        correlation_id: UUID,
        max_attempts: int = 5,
        interval_seconds: int | None = None,
        actor_kind: str = "system",
        source: str = "jobs.scheduler",
        now: datetime | None = None,
    ) -> JobSchedule:
        timestamp = _utc(now or datetime.now(timezone.utc))
        schedule = JobSchedule(
            id=uuid4(),
            created_at=timestamp,
            updated_at=timestamp,
            actor_kind=actor_kind,
            actor_id=None,
            source=source,
            correlation_id=correlation_id,
            job_type=job_type,
            logical_target=logical_target,
            schedule_kind=schedule_kind,
            interval_seconds=interval_seconds,
            next_run_at=_utc(next_run_at),
            enabled=True,
            max_attempts=max_attempts,
        )
        self.session.add(schedule)
        self.session.flush()
        return schedule

    def claim_due_schedule(
        self,
        *,
        now: datetime | None = None,
    ) -> JobSchedule | None:
        timestamp = _utc(now or datetime.now(timezone.utc))
        schedule = self.session.scalar(
            select(JobSchedule)
            .where(
                JobSchedule.enabled.is_(True),
                JobSchedule.next_run_at <= timestamp,
            )
            .order_by(JobSchedule.next_run_at)
            .with_for_update(skip_locked=True)
        )
        return schedule

    def advance_schedule(
        self,
        schedule: JobSchedule,
        *,
        now: datetime | None = None,
    ) -> None:
        timestamp = _utc(now or datetime.now(timezone.utc))
        planned = schedule.next_run_at
        schedule.last_scheduled_at = planned
        if schedule.schedule_kind == "one_shot":
            schedule.enabled = False
        else:
            if schedule.interval_seconds is None:
                raise ValueError("fixed interval schedule requires interval_seconds")
            schedule.next_run_at = planned + timedelta(
                seconds=schedule.interval_seconds
            )
        schedule.updated_at = timestamp
        self.session.flush()

    def abandon(
        self, execution: JobExecution, *, now: datetime | None = None
    ) -> None:
        timestamp = _utc(now or datetime.now(timezone.utc))
        execution.available_at = timestamp
        execution.error_code = "job.lease_expired"
        execution.lease_owner = None
        execution.lease_until = None
        execution.updated_at = timestamp
        if execution.attempt_count < execution.max_attempts:
            execution.state = "retry_wait"
            self.create_outbox(
                execution,
                attempt_number=execution.attempt_count + 1,
                available_at=timestamp,
                now=timestamp,
            )
        else:
            execution.state = "failed"
            execution.finished_at = timestamp
        self.session.flush()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


JobExecutionRepository = SqlAlchemyJobRepository
JobOutboxRepository = SqlAlchemyJobRepository
JobScheduleRepository = SqlAlchemyJobRepository

__all__ = [
    "JobExecutionRepository",
    "JobOutboxRepository",
    "JobScheduleRepository",
    "SqlAlchemyJobRepository",
]
