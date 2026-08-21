"""Pure, transport-independent values and errors for Bronze ingestion."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from umbral.domain.audit import AuditActor

ImportFormat = Literal["csv", "json"]
ImportRunState = Literal["pending", "running", "succeeded", "failed"]

_SAFE_SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
_SAFE_VERSION_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_SAFE_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._(){}[\]-]{0,199}$")


def normalize_source_id(value: str) -> str:
    normalized = value.strip().lower()
    if not _SAFE_SOURCE_RE.fullmatch(normalized):
        raise ValueError("source_id must be a bounded lowercase identifier")
    return normalized


def normalize_source_version(value: str) -> str:
    normalized = value.strip().lower()
    if not _SAFE_VERSION_RE.fullmatch(normalized):
        raise ValueError("source_version must be a bounded lowercase identifier")
    return normalized


def normalize_contract_version(value: str) -> str:
    normalized = value.strip()
    if normalized != "2":
        raise ValueError("unsupported contract_version")
    return normalized


def normalize_batch_key(value: str) -> str:
    normalized = value.strip()
    if not _SAFE_KEY_RE.fullmatch(normalized):
        raise ValueError("batch_key must be a bounded opaque key")
    return normalized


def normalize_file_name(value: str) -> str:
    """Return the safe basename of an uploaded file, never a path."""
    base = Path(value.replace("\\", "/")).name.strip()
    if not _SAFE_FILE_RE.fullmatch(base):
        raise ValueError("file_name must be a bounded safe basename")
    return base


def raw_content_type(file_format: ImportFormat) -> str:
    return "text/csv" if file_format == "csv" else "application/json"


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    source_id: str
    source_version: str
    contract_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", normalize_source_id(self.source_id))
        object.__setattr__(
            self, "source_version", normalize_source_version(self.source_version)
        )
        object.__setattr__(
            self, "contract_version", normalize_contract_version(self.contract_version)
        )


@dataclass(frozen=True, slots=True)
class ImportBatchRequest:
    """Command to submit one controlled batch."""

    source: SourceIdentity
    batch_key: str
    file_format: ImportFormat
    file_name: str
    raw: bytes
    actor: AuditActor
    correlation_id: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.raw, bytes) or not self.raw:
            raise ValueError("raw batch content must be non-empty bytes")
        if self.file_format not in {"csv", "json"}:
            raise ValueError("file_format must be csv or json")
        object.__setattr__(self, "batch_key", normalize_batch_key(self.batch_key))
        object.__setattr__(self, "file_name", normalize_file_name(self.file_name))


@dataclass(frozen=True, slots=True)
class ParsedRecord:
    payload: Mapping[str, object]
    raw_bytes: bytes
    published_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ParsedError:
    index: int
    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class ParsedBatch:
    records: tuple[ParsedRecord, ...]
    parse_errors: tuple[ParsedError, ...]

    @property
    def total(self) -> int:
        return len(self.records) + len(self.parse_errors)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    rule: str
    detail: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    issues: tuple[ValidationIssue, ...]
    missing_optional: int = 0


@dataclass(frozen=True, slots=True)
class RunCounts:
    total_records: int
    accepted: int
    quarantined: int
    duplicates: int
    missing_fields: int


@dataclass(slots=True)
class ImportRun:
    run_id: UUID
    source: SourceIdentity
    batch_key: str
    file_format: ImportFormat
    file_name: str
    file_sha256: str
    file_size_bytes: int
    raw_storage_key: str
    job_execution_id: UUID | None
    state: ImportRunState
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None
    total_records: int = 0
    accepted: int = 0
    quarantined: int = 0
    duplicates: int = 0
    missing_fields: int = 0
    error_code: str | None = None
    error_detail: str | None = None
    version: int = 1

    def snapshot(self) -> "ImportRunSnapshot":
        return ImportRunSnapshot(
            run_id=self.run_id,
            source=self.source,
            batch_key=self.batch_key,
            file_format=self.file_format,
            file_name=self.file_name,
            file_sha256=self.file_sha256,
            state=self.state,
            created_at=self.created_at,
            finished_at=self.finished_at,
            total_records=self.total_records,
            accepted=self.accepted,
            quarantined=self.quarantined,
            duplicates=self.duplicates,
            missing_fields=self.missing_fields,
            error_code=self.error_code,
            error_detail=self.error_detail,
        )

    @property
    def counts(self) -> RunCounts:
        return RunCounts(
            total_records=self.total_records,
            accepted=self.accepted,
            quarantined=self.quarantined,
            duplicates=self.duplicates,
            missing_fields=self.missing_fields,
        )


@dataclass(frozen=True, slots=True)
class ImportRunSnapshot:
    run_id: UUID
    source: SourceIdentity
    batch_key: str
    file_format: ImportFormat
    file_name: str
    file_sha256: str
    state: ImportRunState
    created_at: datetime
    finished_at: datetime | None
    total_records: int
    accepted: int
    quarantined: int
    duplicates: int
    missing_fields: int
    error_code: str | None
    error_detail: str | None

    @property
    def counts(self) -> RunCounts:
        return RunCounts(
            total_records=self.total_records,
            accepted=self.accepted,
            quarantined=self.quarantined,
            duplicates=self.duplicates,
            missing_fields=self.missing_fields,
        )


@dataclass(frozen=True, slots=True)
class RawListingSnapshot:
    snapshot_id: UUID
    run_id: UUID
    source: SourceIdentity
    external_id: str
    payload: Mapping[str, object]
    content_sha256: str
    content_type: str
    size_bytes: int
    published_at: datetime | None
    captured_at: datetime


@dataclass(frozen=True, slots=True)
class QuarantineRecord:
    record_id: UUID
    run_id: UUID
    source: SourceIdentity
    external_id: str | None
    code: str
    rule: str
    detail: str
    payload: Mapping[str, object] | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AbnormalDistribution:
    field: str
    signal: str
    detail: str


@dataclass(frozen=True, slots=True)
class QualityReport:
    run_id: UUID
    counts: RunCounts
    missing_fields_by_name: Mapping[str, int]
    abnormal_distributions: tuple[AbnormalDistribution, ...]


class IngestionError(Exception):
    """Base class for sanitized ingestion failures."""

    code = "ingestion.error"


class BatchRejected(IngestionError):
    """The whole batch violates a file-level contract rule."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


class IngestionPermanentError(IngestionError):
    """A terminal processing failure with an actionable code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


class IngestionTransientError(IngestionError):
    """A bounded, retryable failure explicitly declared by the worker."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


class ImportRunNotFound(IngestionError):
    code = "ingestion.run_not_found"

    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        super().__init__(f"import run not found: {run_id}")


class RunNotTerminalError(IngestionError):
    code = "ingestion.run_not_terminal"

    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        super().__init__(f"import run is not terminal: {run_id}")
