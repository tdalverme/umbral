"""Application ports for durable jobs; infrastructure supplies adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
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
    def submit(self, command: SubmitJob) -> JobSnapshot: ...

    def get(self, execution_id: UUID) -> JobSnapshot: ...


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
