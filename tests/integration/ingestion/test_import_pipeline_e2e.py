"""US1 end-to-end: submit, worker capture and operator reads (real backend)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from tests.integration.ingestion.conftest import IngestionBackend

from umbral.application.ingestion.contracts import ImportBatchRequest, SourceIdentity
from umbral.application.ingestion.import_contract import ContractSpec
from umbral.application.jobs.contracts import JobState, SubmitJob
from umbral.domain.audit import AuditActor
from umbral.infrastructure.ingestion.composition import build_ingestion_service
from umbral.infrastructure.jobs.runtime import SqlAlchemyJobRuntime
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.workers.imports import IngestionImportHandler

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


def test_operator_import_and_run_read_end_to_end(
    ingestion_backend: IngestionBackend, ingestion_contract: ContractSpec
) -> None:
    factory, object_store, _ = ingestion_backend
    runtime = SqlAlchemyJobRuntime(factory, queue=RecordingJobQueue())
    service = build_ingestion_service(
        session_factory=factory,
        object_store=object_store,
        job_runtime=runtime,
        contract=ingestion_contract,
        clock=lambda: datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    handler = IngestionImportHandler(service)
    runtime = SqlAlchemyJobRuntime(
        factory,
        queue=RecordingJobQueue(),
        handlers={"ingestion.import_batch": handler},
    )
    service.job_runtime = runtime

    submitted = service.submit(_request("e2e-1"))
    assert submitted.state == "pending"

    job = runtime.submit(
        SubmitJob.create(
            job_type="ingestion.import_batch",
            logical_target="source-a:e2e-1",
            idempotency_key="e2e-1",
        )
    )
    claim = runtime.claim(
        execution_id=job.execution_id, attempt_number=1, worker_id="w1"
    )
    assert claim is not None
    outcome = runtime.record_outcome(claim, handler.run(claim.context))
    assert outcome.state == JobState.SUCCEEDED
    assert outcome.result is not None
    assert outcome.result["accepted"] == 9

    run = service.get(submitted.run_id)
    assert run.state == "succeeded"
    assert run.total_records == 12

    report = service.quality(run.run_id)
    assert report.counts.accepted == 9
    assert len(service.quarantine_records(run.run_id)) == 2
