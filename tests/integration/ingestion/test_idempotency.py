"""US2 idempotency: repeats and interruptions never duplicate effects."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from tests.fakes.imports import (
    InMemoryImportRunRepository,
    InMemoryRawSnapshotRepository,
    make_import_service,
)

from umbral.application.ingestion.contracts import ImportBatchRequest, SourceIdentity
from umbral.application.ingestion.service import ImportRunService
from umbral.application.jobs.contracts import JobSnapshot, JobState, SubmitJob
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.domain.audit import AuditActor
from umbral.infrastructure.ingestion.contract_loader import load_contract_v1
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.workers.imports import IngestionImportHandler

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures" / "imports"
CONTRACT = load_contract_v1()
NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _request(
    batch_key: str,
    raw: bytes | None = None,
    file_format: Literal["csv", "json"] = "json",
) -> ImportBatchRequest:
    return ImportBatchRequest(
        source=SourceIdentity("source-a", "v1", "1"),
        batch_key=batch_key,
        file_format=file_format,
        file_name="reference-batch.json",
        raw=raw or (FIXTURES / "reference-batch.json").read_bytes(),
        actor=AuditActor(kind="operator", id="operator-1"),
        correlation_id=uuid4(),
    )


def _service_with_handler(
    snapshots: InMemoryRawSnapshotRepository | None = None,
) -> tuple[
    ImportRunService,
    InMemoryImportRunRepository,
    InMemoryJobRuntime,
    IngestionImportHandler,
]:
    service, runs = make_import_service(contract=CONTRACT, now=NOW, snapshots=snapshots)
    handler = IngestionImportHandler(service)
    runtime = InMemoryJobRuntime(
        queue=RecordingJobQueue(), now=NOW, handlers={"ingestion.import_batch": handler}
    )
    service.job_runtime = runtime
    return service, runs, runtime, handler


def _run_once(
    runtime: InMemoryJobRuntime, handler: IngestionImportHandler, batch_key: str
) -> JobSnapshot:
    snapshot = runtime.submit(
        SubmitJob.create(
            job_type="ingestion.import_batch",
            logical_target=f"source-a:{batch_key}",
            idempotency_key=batch_key,
        )
    )
    claim = runtime.claim(
        execution_id=snapshot.execution_id, attempt_number=1, worker_id="w1"
    )
    assert claim is not None
    return runtime.record_outcome(claim, handler.run(claim.context))


def test_repeat_same_key_returns_existing_run_without_new_effects() -> None:
    service, runs, runtime, handler = _service_with_handler()
    service.submit(_request("batch-key-1"))
    first = _run_once(runtime, handler, "batch-key-1")
    service.submit(_request("batch-key-1"))  # same key: no new run/effect
    replay = runtime.submit(
        SubmitJob.create(
            job_type="ingestion.import_batch",
            logical_target="source-a:batch-key-1",
            idempotency_key="batch-key-1",
        )
    )

    assert first.state == JobState.SUCCEEDED
    assert replay.state == JobState.SUCCEEDED
    assert replay.result == first.result
    assert len(runs.runs) == 1


def test_same_content_new_key_creates_no_duplicate_snapshots() -> None:
    snapshots = InMemoryRawSnapshotRepository()
    service, runs, runtime, handler = _service_with_handler(snapshots)

    service.submit(_request("k1"))
    first = _run_once(runtime, handler, "k1")
    service.submit(_request("k2"))
    second = _run_once(runtime, handler, "k2")

    assert first.result is not None
    assert first.result["accepted"] == 9
    assert second.result is not None
    assert second.result["accepted"] == 0
    assert second.result["duplicates"] == 10
    assert len(snapshots.snapshots) == 9
    assert len(runs.runs) == 2


def test_interrupted_retry_commits_no_duplicate_rows() -> None:
    snapshots = InMemoryRawSnapshotRepository()
    service, runs, runtime, handler = _service_with_handler(snapshots)

    service.submit(_request("k1"))
    snapshot = runtime.submit(
        SubmitJob.create(
            job_type="ingestion.import_batch",
            logical_target="source-a:k1",
            idempotency_key="k1",
        )
    )
    claim = runtime.claim(
        execution_id=snapshot.execution_id, attempt_number=1, worker_id="w1"
    )
    assert claim is not None
    outcome = runtime.record_outcome(claim, handler.run(claim.context))
    assert outcome.state == JobState.SUCCEEDED

    # Ack-lost retry over the same execution: no duplicate rows.
    retry = service.process(snapshot.execution_id)
    assert retry.accepted == 9
    assert len(snapshots.snapshots) == 9
    assert len(runs.runs) == 1
