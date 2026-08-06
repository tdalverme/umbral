"""IngestionImportHandler: durable job execution through the runtime."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from tests.fakes.imports import make_import_service

from umbral.application.ingestion.contracts import ImportBatchRequest, SourceIdentity
from umbral.application.ingestion.service import ImportRunService
from umbral.application.jobs.contracts import (
    JobContext,
    JobSnapshot,
    JobState,
    SubmitJob,
    TransientJobError,
)
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.domain.audit import AuditActor
from umbral.infrastructure.ingestion.contract_loader import load_contract_v1
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.workers.imports import IngestionImportHandler

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "tests" / "fixtures" / "imports"
CONTRACT = load_contract_v1()
NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _runtime_with_handler() -> tuple[
    ImportRunService, IngestionImportHandler, InMemoryJobRuntime
]:
    service, _ = make_import_service(contract=CONTRACT, now=NOW)
    handler = IngestionImportHandler(service)
    runtime = InMemoryJobRuntime(
        queue=RecordingJobQueue(),
        now=NOW,
        handlers={"ingestion.import_batch": handler},
    )
    service.job_runtime = runtime
    return service, handler, runtime


def _submit_and_process(
    runtime: InMemoryJobRuntime, handler: IngestionImportHandler
) -> JobSnapshot:
    snapshot = runtime.submit(
        SubmitJob.create(
            job_type="ingestion.import_batch",
            logical_target="source-a:batch-key-1",
            idempotency_key="batch-key-1",
        )
    )
    claim = runtime.claim(
        execution_id=snapshot.execution_id, attempt_number=1, worker_id="w1"
    )
    assert claim is not None
    result = handler.run(claim.context)
    return runtime.record_outcome(claim, result)


def test_handler_captures_a_batch_through_the_job_runtime() -> None:
    service, handler, runtime = _runtime_with_handler()
    service.submit(
        ImportBatchRequest(
            source=SourceIdentity("source-a", "v1", "1"),
            batch_key="batch-key-1",
            file_format="json",
            file_name="reference-batch.json",
            raw=(FIXTURES / "reference-batch.json").read_bytes(),
            actor=AuditActor(kind="operator", id="operator-1"),
            correlation_id=uuid4(),
        )
    )
    finished = _submit_and_process(runtime, handler)

    assert finished.state == JobState.SUCCEEDED
    assert finished.result is not None
    assert finished.result["accepted"] == 9
    assert finished.result["duplicates"] == 1
    assert finished.result["quarantined"] == 2


def test_handler_maps_unknown_run_to_transient_error() -> None:
    _, handler, _ = _runtime_with_handler()
    context = JobContext(
        execution_id=uuid4(),
        attempt_number=1,
        correlation_id=uuid4(),
        release_id="test",
        logical_target="source-a:nope",
    )
    with pytest.raises(TransientJobError):
        handler.run(context)
