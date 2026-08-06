"""Full capture pipeline on real Postgres + object storage (US1)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from tests.integration.ingestion.conftest import IngestionBackend

from umbral.application.ingestion.contracts import (
    ImportBatchRequest,
    SourceIdentity,
)
from umbral.application.ingestion.import_contract import ContractSpec
from umbral.application.ingestion.service import ImportRunService
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.application.objects.contracts import ProviderObjectRef
from umbral.domain.audit import AuditActor
from umbral.infrastructure.db.repositories.imports import (
    SqlAlchemyImportRunRepository,
    SqlAlchemyQuarantineRepository,
    SqlAlchemyRawSnapshotRepository,
)
from umbral.infrastructure.ingestion.composition import build_ingestion_service
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures" / "imports"


def _request(batch_key: str) -> ImportBatchRequest:
    return ImportBatchRequest(
        source=SourceIdentity("source-a", "v1", "1"),
        batch_key=batch_key,
        file_format="json",
        file_name="reference-batch.json",
        raw=(FIXTURES / "reference-batch.json").read_bytes(),
        actor=AuditActor(kind="operator", id="operator-1"),
        correlation_id=uuid4(),
    )


def test_capture_persists_snapshots_quarantine_and_raw_object(
    ingestion_backend: IngestionBackend, ingestion_contract: ContractSpec
) -> None:
    factory, object_store, _ = ingestion_backend
    runtime = InMemoryJobRuntime(queue=RecordingJobQueue())
    service = build_ingestion_service(
        session_factory=factory,
        object_store=object_store,
        job_runtime=runtime,
        contract=ingestion_contract,
        clock=lambda: datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    snapshot = service.submit(_request("pipeline-1"))
    assert snapshot.state == "pending"
    execution_id = runtime.submissions[-1].execution_id
    finished = service.process(execution_id)

    assert finished.state == "succeeded"
    assert finished.accepted == 9
    assert finished.quarantined == 2
    assert finished.duplicates == 1
    assert finished.missing_fields == 3

    snapshots = SqlAlchemyRawSnapshotRepository(factory)
    quarantine = SqlAlchemyQuarantineRepository(factory)
    assert len(snapshots.list_for_run(finished.run_id)) == 9
    assert len(quarantine.list_for_run(finished.run_id)) == 2

    run = SqlAlchemyImportRunRepository(factory).get(finished.run_id)
    assert run is not None
    info = object_store.stat(ProviderObjectRef(run.raw_storage_key))
    assert info.sha256 == run.file_sha256
    assert info.size_bytes == run.file_size_bytes


def test_capture_is_idempotent_on_real_backend(
    ingestion_backend: IngestionBackend, ingestion_contract: ContractSpec
) -> None:
    factory, object_store, _ = ingestion_backend
    runtime = InMemoryJobRuntime(queue=RecordingJobQueue())
    service = build_ingestion_service(
        session_factory=factory,
        object_store=object_store,
        job_runtime=runtime,
        contract=ingestion_contract,
        clock=lambda: datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    snapshots = SqlAlchemyRawSnapshotRepository(factory)

    service.submit(_request("k1"))
    service.process(runtime.submissions[-1].execution_id)
    first_count = len(snapshots.list_for_run(service.get(_run_id(service)).run_id))

    service.submit(_request("k2"))
    second = service.process(runtime.submissions[-1].execution_id)

    assert first_count == 9
    assert second.accepted == 0
    assert second.duplicates == 10
    assert len(snapshots.list_for_run(second.run_id)) == 0


def _run_id(service: ImportRunService) -> UUID:
    runtime = cast(InMemoryJobRuntime, service.job_runtime)
    run = service.runs.find_by_job_execution(runtime.submissions[-1].execution_id)
    assert run is not None
    return run.run_id
