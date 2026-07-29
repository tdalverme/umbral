"""Pure, transport-independent durable-job contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Literal, Mapping
from uuid import UUID, uuid4

from umbral.domain.audit import AuditActor

JsonScalar = str | int | float | bool | None
FailureKind = Literal["transient", "permanent", "unclassified"]


class JobState(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    RETRY_WAIT = "retry_wait"
    FAILED = "failed"


class AttemptState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    TRANSIENT_FAILURE = "transient_failure"
    PERMANENT_FAILURE = "permanent_failure"
    ABANDONED = "abandoned"


_JOB_TYPE_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")


def normalize_job_type(value: str) -> str:
    """Return the canonical lowercase registered-handler identifier."""

    normalized = value.strip().lower()
    if (
        not normalized
        or len(normalized) > 100
        or not _JOB_TYPE_RE.fullmatch(normalized)
    ):
        raise ValueError("job_type must be a lowercase dotted identifier")
    return normalized


def normalize_target(value: str) -> str:
    """Normalize a non-secret, deterministic logical target.

    Targets are opaque to the generic runtime. Query strings, fragments and
    common credential markers are deliberately rejected because they make
    identity unstable or leak secrets into durable metadata.
    """

    normalized = value.strip()
    lowered = normalized.lower()
    if (
        not normalized
        or len(normalized) > 300
        or any(character.isspace() for character in normalized)
        or any(marker in lowered for marker in ("token=", "secret=", "password="))
        or "?" in normalized
        or "#" in normalized
    ):
        raise ValueError("logical target must be stable, bounded and non-secret")
    return normalized


def normalize_idempotency_key(value: str) -> str:
    normalized = value.strip()
    if not _SAFE_KEY_RE.fullmatch(normalized):
        raise ValueError("idempotency_key must be a bounded opaque key")
    return normalized


def is_terminal_state(state: JobState | str) -> bool:
    return str(state) in {JobState.SUCCEEDED.value, JobState.FAILED.value}


@dataclass(frozen=True, slots=True)
class JobIdentity:
    job_type: str
    logical_target: str
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "job_type", normalize_job_type(self.job_type))
        object.__setattr__(
            self, "logical_target", normalize_target(self.logical_target)
        )
        object.__setattr__(
            self, "idempotency_key", normalize_idempotency_key(self.idempotency_key)
        )

    @classmethod
    def create(
        cls, job_type: str, logical_target: str, idempotency_key: str
    ) -> JobIdentity:
        return cls(job_type, logical_target, idempotency_key)

    @property
    def key(self) -> tuple[str, str, str]:
        return self.job_type, self.logical_target, self.idempotency_key


@dataclass(frozen=True, slots=True)
class SubmitJob:
    identity: JobIdentity
    correlation_id: UUID
    actor: AuditActor
    max_attempts: int = 5

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")

    @classmethod
    def create(
        cls,
        *,
        job_type: str,
        logical_target: str,
        idempotency_key: str,
        correlation_id: UUID | None = None,
        actor: AuditActor | None = None,
        max_attempts: int = 5,
    ) -> SubmitJob:
        return cls(
            identity=JobIdentity.create(job_type, logical_target, idempotency_key),
            correlation_id=correlation_id or uuid4(),
            actor=actor or AuditActor.system(),
            max_attempts=max_attempts,
        )


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    execution_id: UUID
    identity: JobIdentity
    state: JobState
    attempt_count: int
    max_attempts: int
    result: Mapping[str, JsonScalar] | None = None
    error_code: str | None = None
    available_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class JobContext:
    execution_id: UUID
    attempt_number: int
    correlation_id: UUID
    release_id: str


class TransientJobError(Exception):
    """A bounded, retryable failure explicitly declared by a handler."""

    def __init__(self, code: str, retry_after: timedelta | None = None) -> None:
        self.code = _normalize_error_code(code)
        self.retry_after = retry_after
        super().__init__(self.code)


class PermanentJobError(Exception):
    """A terminal validation, invariant or authorization failure."""

    def __init__(self, code: str) -> None:
        self.code = _normalize_error_code(code)
        super().__init__(self.code)


class UnclassifiedJobError(Exception):
    """Marker used by tests and adapters for an unexpected exception."""


def _normalize_error_code(code: str) -> str:
    normalized = code.strip().lower()
    if (
        not normalized
        or len(normalized) > 100
        or not re.fullmatch(r"[a-z0-9._-]+", normalized)
    ):
        raise ValueError("error code must be a stable normalized identifier")
    return normalized


@dataclass(frozen=True, slots=True)
class FailureClassification:
    code: str
    kind: FailureKind
    retryable: bool
    occurred_at: datetime


def classify_failure(error: Exception) -> FailureClassification:
    occurred_at = datetime.now(timezone.utc)
    if isinstance(error, TransientJobError):
        return FailureClassification(error.code, "transient", True, occurred_at)
    if isinstance(error, PermanentJobError):
        return FailureClassification(error.code, "permanent", False, occurred_at)
    return FailureClassification(
        "job.unclassified_failure", "unclassified", False, occurred_at
    )
