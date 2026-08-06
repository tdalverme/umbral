"""SQLAlchemy repositories for Bronze ingestion; each method owns its commit."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from umbral.application.ingestion.contracts import (
    ImportFormat,
    ImportRun,
    ImportRunState,
    QuarantineRecord,
    RawListingSnapshot,
    SourceIdentity,
)
from umbral.infrastructure.db.models.imports import (
    ImportRun as ImportRunModel,
)
from umbral.infrastructure.db.models.imports import (
    QuarantineRecord as QuarantineRecordModel,
)
from umbral.infrastructure.db.models.imports import (
    RawListingSnapshot as RawListingSnapshotModel,
)

SessionFactory = Callable[[], Session]


class SqlAlchemyImportRunRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

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
        with self.session_factory() as session:
            model = ImportRunModel(
                id=run_id,
                created_at=now,
                updated_at=now,
                actor_kind=actor_kind,
                actor_id=actor_id,
                source="ingestion.submit",
                correlation_id=correlation_id,
                job_execution_id=job_execution_id,
                batch_key=batch_key,
                source_id=source.source_id,
                source_version=source.source_version,
                contract_version=source.contract_version,
                file_format=file_format,
                file_name=file_name,
                file_sha256=file_sha256,
                file_size_bytes=file_size_bytes,
                raw_storage_key=raw_storage_key,
                state="pending",
                total_records=0,
                accepted=0,
                quarantined=0,
                duplicates=0,
                missing_fields=0,
            )
            session.add(model)
            session.commit()
            return _to_domain_run(model)

    def get(self, run_id: UUID) -> ImportRun | None:
        with self.session_factory() as session:
            model = session.get(ImportRunModel, run_id)
            return _to_domain_run(model) if model is not None else None

    def get_by_identity(self, source_id: str, batch_key: str) -> ImportRun | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(ImportRunModel).where(
                    ImportRunModel.source_id == source_id,
                    ImportRunModel.batch_key == batch_key,
                )
            )
            return _to_domain_run(model) if model is not None else None

    def find_by_job_execution(self, execution_id: UUID) -> ImportRun | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(ImportRunModel).where(
                    ImportRunModel.job_execution_id == execution_id
                )
            )
            return _to_domain_run(model) if model is not None else None

    def save(self, run: ImportRun) -> None:
        with self.session_factory() as session:
            model = session.get(ImportRunModel, run.run_id)
            if model is None:
                raise KeyError(run.run_id)
            model.job_execution_id = run.job_execution_id
            model.state = run.state
            model.total_records = run.total_records
            model.accepted = run.accepted
            model.quarantined = run.quarantined
            model.duplicates = run.duplicates
            model.missing_fields = run.missing_fields
            model.finished_at = run.finished_at
            model.error_code = run.error_code
            model.error_detail = run.error_detail
            model.updated_at = run.updated_at
            session.commit()


class SqlAlchemyRawSnapshotRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def exists(self, *, source_id: str, external_id: str, content_sha256: str) -> bool:
        with self.session_factory() as session:
            row = session.scalar(
                select(RawListingSnapshotModel.id).where(
                    RawListingSnapshotModel.source_id == source_id,
                    RawListingSnapshotModel.external_id == external_id,
                    RawListingSnapshotModel.content_sha256 == content_sha256,
                )
            )
            return row is not None

    def insert(self, snapshot: RawListingSnapshot) -> None:
        with self.session_factory() as session:
            model = RawListingSnapshotModel(
                id=snapshot.snapshot_id,
                created_at=snapshot.captured_at,
                updated_at=snapshot.captured_at,
                actor_kind="system",
                actor_id=None,
                source="ingestion.capture",
                correlation_id=snapshot.run_id,
                run_id=snapshot.run_id,
                source_id=snapshot.source.source_id,
                source_version=snapshot.source.source_version,
                contract_version=snapshot.source.contract_version,
                external_id=snapshot.external_id,
                content_sha256=snapshot.content_sha256,
                payload=dict(snapshot.payload),
                content_type=snapshot.content_type,
                size_bytes=snapshot.size_bytes,
                published_at=snapshot.published_at,
                captured_at=snapshot.captured_at,
            )
            session.add(model)
            session.commit()

    def list_for_run(self, run_id: UUID) -> tuple[RawListingSnapshot, ...]:
        with self.session_factory() as session:
            models = session.scalars(
                select(RawListingSnapshotModel)
                .where(RawListingSnapshotModel.run_id == run_id)
                .order_by(RawListingSnapshotModel.created_at)
            )
            return tuple(_to_domain_snapshot(model) for model in models)

    def get(self, snapshot_id: UUID) -> RawListingSnapshot | None:
        with self.session_factory() as session:
            model = session.get(RawListingSnapshotModel, snapshot_id)
            return _to_domain_snapshot(model) if model is not None else None


class SqlAlchemyQuarantineRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert(self, record: QuarantineRecord) -> None:
        with self.session_factory() as session:
            model = QuarantineRecordModel(
                id=record.record_id,
                created_at=record.created_at,
                updated_at=record.created_at,
                actor_kind="system",
                actor_id=None,
                source="ingestion.capture",
                correlation_id=record.run_id,
                run_id=record.run_id,
                source_id=record.source.source_id,
                source_version=record.source.source_version,
                contract_version=record.source.contract_version,
                external_id=record.external_id,
                code=record.code,
                rule=record.rule,
                detail=record.detail,
                payload=dict(record.payload) if record.payload is not None else None,
            )
            session.add(model)
            session.commit()

    def list_for_run(self, run_id: UUID) -> tuple[QuarantineRecord, ...]:
        with self.session_factory() as session:
            models = session.scalars(
                select(QuarantineRecordModel)
                .where(QuarantineRecordModel.run_id == run_id)
                .order_by(QuarantineRecordModel.created_at)
            )
            return tuple(_to_domain_quarantine(model) for model in models)

    def get(self, record_id: UUID) -> QuarantineRecord | None:
        with self.session_factory() as session:
            model = session.get(QuarantineRecordModel, record_id)
            return _to_domain_quarantine(model) if model is not None else None


def _to_domain_run(model: ImportRunModel) -> ImportRun:
    return ImportRun(
        run_id=model.id,
        source=SourceIdentity(
            source_id=model.source_id,
            source_version=model.source_version,
            contract_version=model.contract_version,
        ),
        batch_key=model.batch_key,
        file_format=cast(ImportFormat, model.file_format),
        file_name=model.file_name,
        file_sha256=model.file_sha256,
        file_size_bytes=model.file_size_bytes,
        raw_storage_key=model.raw_storage_key,
        job_execution_id=model.job_execution_id,
        state=cast(ImportRunState, model.state),
        created_at=model.created_at,
        updated_at=model.updated_at,
        finished_at=model.finished_at,
        total_records=model.total_records,
        accepted=model.accepted,
        quarantined=model.quarantined,
        duplicates=model.duplicates,
        missing_fields=model.missing_fields,
        error_code=model.error_code,
        error_detail=model.error_detail,
        version=model.version,
    )


def _to_domain_snapshot(model: RawListingSnapshotModel) -> RawListingSnapshot:
    return RawListingSnapshot(
        snapshot_id=model.id,
        run_id=model.run_id,
        source=SourceIdentity(
            source_id=model.source_id,
            source_version=model.source_version,
            contract_version=model.contract_version,
        ),
        external_id=model.external_id,
        payload=model.payload,
        content_sha256=model.content_sha256,
        content_type=model.content_type,
        size_bytes=model.size_bytes,
        published_at=model.published_at,
        captured_at=model.captured_at,
    )


def _to_domain_quarantine(model: QuarantineRecordModel) -> QuarantineRecord:
    return QuarantineRecord(
        record_id=model.id,
        run_id=model.run_id,
        source=SourceIdentity(
            source_id=model.source_id,
            source_version=model.source_version,
            contract_version=model.contract_version,
        ),
        external_id=model.external_id,
        code=model.code,
        rule=model.rule,
        detail=model.detail,
        payload=model.payload,
        created_at=model.created_at,
    )
