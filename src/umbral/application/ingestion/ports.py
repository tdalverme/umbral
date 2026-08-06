"""Application ports for controlled ingestion; infrastructure supplies adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from umbral.application.ingestion.contracts import (
    ImportFormat,
    ImportRun,
    ParsedBatch,
    QuarantineRecord,
    RawListingSnapshot,
    SourceIdentity,
)


class ImportSource(Protocol):
    """Reads raw batch bytes into records and a report, never into Silver."""

    def read_batch(
        self, *, raw: bytes, file_format: ImportFormat, file_name: str
    ) -> ParsedBatch: ...


class ImportRunRepository(Protocol):
    def create(
        self,
        *,
        run_id: UUID,
        source: SourceIdentity,
        batch_key: str,
        file_format: ImportFormat,
        file_name: str,
        file_sha256: str,
        file_size_bytes: int,
        raw_storage_key: str,
        job_execution_id: UUID | None,
        correlation_id: UUID,
        actor_kind: str,
        actor_id: str | None,
        now: datetime,
    ) -> ImportRun: ...

    def get(self, run_id: UUID) -> ImportRun | None: ...

    def get_by_identity(self, source_id: str, batch_key: str) -> ImportRun | None: ...

    def find_by_job_execution(self, execution_id: UUID) -> ImportRun | None: ...

    def save(self, run: ImportRun) -> None: ...


class RawSnapshotRepository(Protocol):
    def exists(
        self, *, source_id: str, external_id: str, content_sha256: str
    ) -> bool: ...

    def insert(self, snapshot: RawListingSnapshot) -> None: ...

    def list_for_run(self, run_id: UUID) -> tuple[RawListingSnapshot, ...]: ...


class QuarantineRepository(Protocol):
    def insert(self, record: QuarantineRecord) -> None: ...

    def list_for_run(self, run_id: UUID) -> tuple[QuarantineRecord, ...]: ...

    def get(self, record_id: UUID) -> QuarantineRecord | None: ...
