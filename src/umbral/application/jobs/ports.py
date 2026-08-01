"""Application ports for durable jobs; infrastructure supplies adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from .contracts import JobContext, JobIdentity, JobSnapshot, JsonScalar, SubmitJob


@dataclass(frozen=True, slots=True)
class JobClaim:
    execution_id: UUID
    attempt_number: int
    worker_id: str
    context: JobContext


@dataclass(frozen=True, slots=True)
class RelayResult:
    published: int = 0
    failed: int = 0


class JobQueue(Protocol):
    def publish(
        self,
        *,
        execution_id: UUID,
        attempt_number: int,
        correlation_id: UUID,
    ) -> str: ...


class JobHandler(Protocol):
    job_type: str

    def normalize_target(self, raw_target: str) -> str: ...

    def run(self, context: JobContext) -> Mapping[str, JsonScalar]: ...


class JobRuntime(Protocol):
    release_id: str

    def submit(self, command: SubmitJob) -> JobSnapshot: ...

    def get(self, execution_id: UUID) -> JobSnapshot: ...

    def identity(self, execution_id: UUID) -> JobIdentity: ...

    def correlation_id(self, execution_id: UUID) -> UUID: ...

    def claim(
        self, *, execution_id: UUID, attempt_number: int, worker_id: str
    ) -> JobClaim | None: ...

    def record_outcome(
        self, claim: JobClaim, outcome: Mapping[str, object] | Exception
    ) -> JobSnapshot: ...

    def relay_due(
        self, *, queue: JobQueue | None = None, limit: int = 100
    ) -> RelayResult: ...

    def reclaim_expired_outbox(self, *, limit: int = 100) -> int: ...

    def reap_expired(self, *, limit: int = 100) -> int: ...

    def rebuild_outbox(self, *, limit: int = 100) -> int: ...

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
    ) -> UUID: ...

    def schedule_tick(self) -> int: ...

    def advance_time(self, delta: timedelta) -> None: ...


class JobRepository(Protocol):
    """Specific persistence seam; methods never commit their own transaction."""

    def get_by_identity(self, identity: JobIdentity) -> object | None: ...

    def get(self, execution_id: UUID) -> object | None: ...

    def claim(
        self,
        execution_id: UUID,
        attempt_number: int,
        *,
        worker_id: str,
        now: datetime,
    ) -> object | None: ...
