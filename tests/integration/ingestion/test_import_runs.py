"""Repository persistence and run state transitions on real PostgreSQL."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from tests.integration.ingestion.conftest import IngestionBackend

from umbral.application.ingestion.contracts import SourceIdentity
from umbral.infrastructure.db.repositories.imports import (
    SqlAlchemyImportRunRepository,
    SqlAlchemyQuarantineRepository,
    SqlAlchemyRawSnapshotRepository,
)

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def test_run_lifecycle_and_identity_lookup(
    ingestion_backend: IngestionBackend,
) -> None:
    factory, _, _ = ingestion_backend
    runs = SqlAlchemyImportRunRepository(factory)
    source = SourceIdentity("source-a", "v1", "1")
    run = runs.create(
        run_id=uuid4(),
        source=source,
        batch_key="batch-key-1",
        file_format="json",
        file_name="reference-batch.json",
        file_sha256="a" * 64,
        file_size_bytes=1024,
        raw_storage_key="ingestion/raw/" + "a" * 64,
        job_execution_id=uuid4(),
        correlation_id=uuid4(),
        actor_kind="operator",
        actor_id="operator-1",
        now=NOW,
    )
    assert run.state == "pending"
    assert runs.get(run.run_id) is not None
    assert runs.get_by_identity("source-a", "batch-key-1") is not None
    assert run.job_execution_id is not None
    assert runs.find_by_job_execution(run.job_execution_id) is not None


def test_run_state_transitions_are_saved(
    ingestion_backend: IngestionBackend,
) -> None:
    factory, _, _ = ingestion_backend
    runs = SqlAlchemyImportRunRepository(factory)
    source = SourceIdentity("source-a", "v1", "1")
    run = runs.create(
        run_id=uuid4(),
        source=source,
        batch_key="batch-key-2",
        file_format="json",
        file_name="reference-batch.json",
        file_sha256="b" * 64,
        file_size_bytes=1024,
        raw_storage_key="ingestion/raw/" + "b" * 64,
        job_execution_id=uuid4(),
        correlation_id=uuid4(),
        actor_kind="operator",
        actor_id="operator-1",
        now=NOW,
    )
    run.state = "running"
    run.updated_at = NOW
    runs.save(run)
    run.state = "succeeded"
    run.finished_at = NOW
    run.total_records = 12
    run.accepted = 9
    run.quarantined = 2
    run.duplicates = 1
    run.missing_fields = 3
    run.updated_at = NOW
    runs.save(run)

    loaded = runs.get(run.run_id)
    assert loaded is not None
    assert loaded.state == "succeeded"
    assert loaded.accepted == 9
    assert loaded.duplicates == 1


def test_snapshot_and_quarantine_repositories(
    ingestion_backend: IngestionBackend,
) -> None:
    factory, _, _ = ingestion_backend
    runs = SqlAlchemyImportRunRepository(factory)
    snapshots = SqlAlchemyRawSnapshotRepository(factory)
    quarantine = SqlAlchemyQuarantineRepository(factory)
    source = SourceIdentity("source-a", "v1", "1")
    run = runs.create(
        run_id=uuid4(),
        source=source,
        batch_key="batch-key-3",
        file_format="json",
        file_name="reference-batch.json",
        file_sha256="c" * 64,
        file_size_bytes=1024,
        raw_storage_key="ingestion/raw/" + "c" * 64,
        job_execution_id=uuid4(),
        correlation_id=uuid4(),
        actor_kind="operator",
        actor_id="operator-1",
        now=NOW,
    )
    from umbral.application.ingestion.contracts import (
        QuarantineRecord,
        RawListingSnapshot,
    )

    snapshot = RawListingSnapshot(
        snapshot_id=uuid4(),
        run_id=run.run_id,
        source=source,
        external_id="list-1",
        payload={"external_id": "list-1"},
        content_sha256="d" * 64,
        content_type="application/json",
        size_bytes=50,
        published_at=None,
        captured_at=NOW,
    )
    snapshots.insert(snapshot)
    assert snapshots.exists(
        source_id="source-a", external_id="list-1", content_sha256="d" * 64
    )
    assert len(snapshots.list_for_run(run.run_id)) == 1

    record = QuarantineRecord(
        record_id=uuid4(),
        run_id=run.run_id,
        source=source,
        external_id="bad-1",
        code="contract.range_invalid",
        rule="field.price",
        detail="price must be greater than 0",
        payload={"price": -1},
        created_at=NOW,
    )
    quarantine.insert(record)
    assert quarantine.get(record.record_id) is not None
    assert len(quarantine.list_for_run(run.run_id)) == 1

