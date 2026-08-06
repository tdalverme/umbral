"""In-memory ingestion adapters and composition helper for application tests."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import BinaryIO
from uuid import UUID

from umbral.application.ingestion.contracts import (
    ImportFormat,
    ImportRun,
    QuarantineRecord,
    RawListingSnapshot,
    SourceIdentity,
)
from umbral.application.ingestion.import_contract import ContractSpec
from umbral.application.ingestion.ports import ImportSource
from umbral.application.ingestion.service import ImportRunService
from umbral.application.jobs.ports import JobRuntime
from umbral.application.objects.contracts import (
    ObjectInfo,
    ObjectVersionConflict,
    ProviderObjectRef,
)
from umbral.application.objects.ports import ObjectStore


class InMemoryImportRunRepository:
    def __init__(self) -> None:
        self.runs: dict[UUID, ImportRun] = {}
        self.identity_index: dict[tuple[str, str], UUID] = {}
        self.execution_index: dict[UUID, UUID] = {}

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
    ) -> ImportRun:
        run = ImportRun(
            run_id=run_id,
            source=source,
            batch_key=batch_key,
            file_format=file_format,
            file_name=file_name,
            file_sha256=file_sha256,
            file_size_bytes=file_size_bytes,
            raw_storage_key=raw_storage_key,
            job_execution_id=job_execution_id,
            state="pending",
            created_at=now,
            updated_at=now,
        )
        self._store(run)
        return run

    def _store(self, run: ImportRun) -> None:
        self.runs[run.run_id] = run
        self.identity_index[(run.source.source_id, run.batch_key)] = run.run_id
        if run.job_execution_id is not None:
            self.execution_index[run.job_execution_id] = run.run_id

    def get(self, run_id: UUID) -> ImportRun | None:
        return self.runs.get(run_id)

    def get_by_identity(self, source_id: str, batch_key: str) -> ImportRun | None:
        run_id = self.identity_index.get((source_id, batch_key))
        return self.runs.get(run_id) if run_id is not None else None

    def find_by_job_execution(self, execution_id: UUID) -> ImportRun | None:
        run_id = self.execution_index.get(execution_id)
        return self.runs.get(run_id) if run_id is not None else None

    def save(self, run: ImportRun) -> None:
        run.version += 1
        self._store(run)


class InMemoryRawSnapshotRepository:
    def __init__(self) -> None:
        self.snapshots: dict[UUID, RawListingSnapshot] = {}
        self.keys: set[tuple[str, str, str]] = set()

    def exists(self, *, source_id: str, external_id: str, content_sha256: str) -> bool:
        return (source_id, external_id, content_sha256) in self.keys

    def insert(self, snapshot: RawListingSnapshot) -> None:
        key = (snapshot.source.source_id, snapshot.external_id, snapshot.content_sha256)
        if key in self.keys:
            return
        self.snapshots[snapshot.snapshot_id] = snapshot
        self.keys.add(key)

    def list_for_run(self, run_id: UUID) -> tuple[RawListingSnapshot, ...]:
        return tuple(
            snapshot
            for snapshot in self.snapshots.values()
            if snapshot.run_id == run_id
        )


class InMemoryQuarantineRepository:
    def __init__(self) -> None:
        self.records: dict[UUID, QuarantineRecord] = {}

    def insert(self, record: QuarantineRecord) -> None:
        self.records[record.record_id] = record

    def list_for_run(self, run_id: UUID) -> tuple[QuarantineRecord, ...]:
        return tuple(
            record for record in self.records.values() if record.run_id == run_id
        )

    def get(self, record_id: UUID) -> QuarantineRecord | None:
        return self.records.get(record_id)


class InMemoryObjectStore:
    """Tiny immutable object adapter used only by application tests."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str, int, str]] = {}

    def put_if_absent(
        self,
        *,
        storage_key: str,
        body: BinaryIO,
        sha256: str,
        size_bytes: int,
        content_type: str,
    ) -> ProviderObjectRef:
        data = body.read()
        if not isinstance(data, bytes):
            raise ValueError("object body must be bytes")
        existing = self.objects.get(storage_key)
        if existing is not None:
            if existing[1] != sha256 or existing[2] != size_bytes:
                raise ObjectVersionConflict("immutable object version conflicts")
            return ProviderObjectRef(storage_key)
        self.objects[storage_key] = (data, sha256, size_bytes, content_type)
        return ProviderObjectRef(storage_key)

    def open(self, provider_ref: ProviderObjectRef) -> BinaryIO:
        data = self.objects.get(provider_ref.value)
        if data is None:
            from umbral.application.objects.contracts import ObjectNotFound

            raise ObjectNotFound("object is unavailable")
        return BytesIO(data[0])

    def stat(self, provider_ref: ProviderObjectRef) -> ObjectInfo:
        data = self.objects.get(provider_ref.value)
        if data is None:
            from umbral.application.objects.contracts import ObjectNotFound

            raise ObjectNotFound("object is unavailable")
        return ObjectInfo(
            provider_ref=provider_ref,
            sha256=data[1],
            size_bytes=data[2],
            content_type=data[3],
        )


def make_import_service(
    *,
    runs: InMemoryImportRunRepository | None = None,
    snapshots: InMemoryRawSnapshotRepository | None = None,
    quarantine: InMemoryQuarantineRepository | None = None,
    source: ImportSource | None = None,
    contract: ContractSpec,
    objects: ObjectStore | None = None,
    job_runtime: JobRuntime | None = None,
    now: datetime | None = None,
) -> tuple[ImportRunService, InMemoryImportRunRepository]:
    from umbral.application.jobs.service import InMemoryJobRuntime
    from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
    from umbral.infrastructure.sources.file_source import FileImportSource

    run_repo = runs or InMemoryImportRunRepository()
    snapshot_repo = snapshots or InMemoryRawSnapshotRepository()
    quarantine_repo = quarantine or InMemoryQuarantineRepository()
    source_adapter = source or FileImportSource()
    object_seam = objects or InMemoryObjectStore()
    runtime = job_runtime or InMemoryJobRuntime(queue=RecordingJobQueue())
    service = ImportRunService(
        runs=run_repo,
        snapshots=snapshot_repo,
        quarantine=quarantine_repo,
        source=source_adapter,
        contract=contract,
        objects=object_seam,
        job_runtime=runtime,
        clock=lambda: now or datetime.now(),
    )
    return service, run_repo
