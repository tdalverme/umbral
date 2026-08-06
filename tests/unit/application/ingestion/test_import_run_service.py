"""ImportRunService: submit, idempotent capture and derived counts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import pytest
from tests.fakes.imports import (
    InMemoryRawSnapshotRepository,
    make_import_service,
)

from umbral.application.ingestion.contracts import (
    BatchRejected,
    ImportBatchRequest,
    IngestionTransientError,
    SourceIdentity,
)
from umbral.application.ingestion.service import ImportRunService
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.domain.audit import AuditActor
from umbral.infrastructure.ingestion.contract_loader import load_contract_v1

ROOT = Path(__file__).resolve().parents[4]
FIXTURES = ROOT / "tests" / "fixtures" / "imports"

CONTRACT = load_contract_v1()
NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _request(
    *,
    batch_key: str = "batch-key-1",
    file_format: Literal["csv", "json"] = "json",
    file_name: str = "reference-batch.json",
    raw: bytes | None = None,
    contract_version: str = "1",
) -> ImportBatchRequest:
    return ImportBatchRequest(
        source=SourceIdentity("source-a", "v1", contract_version),
        batch_key=batch_key,
        file_format=file_format,
        file_name=file_name,
        raw=raw or (FIXTURES / file_name).read_bytes(),
        actor=AuditActor(kind="operator", id="operator-1"),
        correlation_id=uuid4(),
    )


def test_submit_creates_pending_run_and_stages_raw_object() -> None:
    service, runs = make_import_service(contract=CONTRACT, now=NOW)
    snapshot = service.submit(_request())

    assert snapshot.state == "pending"
    assert snapshot.run_id is not None
    run = runs.get(snapshot.run_id)
    assert run is not None
    assert run.job_execution_id is not None
    assert run.raw_storage_key.startswith("ingestion/raw/")


def test_submit_is_idempotent_by_source_and_batch_key() -> None:
    service, _ = make_import_service(contract=CONTRACT, now=NOW)
    first = service.submit(_request(batch_key="same-key"))
    second = service.submit(_request(batch_key="same-key"))
    assert first.run_id == second.run_id


def test_submit_rejects_unsupported_contract_version() -> None:
    service, _ = make_import_service(contract=CONTRACT, now=NOW)
    with pytest.raises(ValueError):
        _request(contract_version="9")


def test_submit_rejects_file_level_violations() -> None:
    service, _ = make_import_service(contract=CONTRACT, now=NOW)
    with pytest.raises(BatchRejected) as error:
        service.submit(
            _request(batch_key="bad", file_name="bad.json", raw=b"\xff\xfe\x00")
        )
    assert error.value.code == "file.encoding_invalid"


def test_process_captures_the_reference_batch() -> None:
    service, _ = make_import_service(contract=CONTRACT, now=NOW)
    service.submit(_request())
    runtime = service.job_runtime
    assert isinstance(runtime, InMemoryJobRuntime)
    execution_id = runtime.submissions[-1].execution_id

    finished = service.process(execution_id)

    assert finished.state == "succeeded"
    assert finished.total_records == 12
    assert finished.accepted == 9
    assert finished.quarantined == 2
    assert finished.duplicates == 1
    assert finished.missing_fields == 3


def test_process_is_idempotent_on_terminal_replay() -> None:
    service, _ = make_import_service(contract=CONTRACT, now=NOW)
    service.submit(_request())
    runtime = service.job_runtime
    assert isinstance(runtime, InMemoryJobRuntime)
    execution_id = runtime.submissions[-1].execution_id
    service.process(execution_id)
    again = service.process(execution_id)
    assert again.accepted == 9
    assert again.duplicates == 1


def test_same_content_new_key_creates_no_duplicate_snapshots() -> None:
    snapshots = InMemoryRawSnapshotRepository()
    service, runs = make_import_service(contract=CONTRACT, now=NOW, snapshots=snapshots)
    service.submit(_request(batch_key="k1"))
    first = service.process(_execution(service))
    assert first.accepted == 9

    service.submit(_request(batch_key="k2"))
    second = service.process(_execution(service))

    assert second.accepted == 0
    assert second.duplicates == 10
    assert second.quarantined == 2
    assert len(snapshots.list_for_run(first.run_id)) == 9


def test_unknown_execution_is_transient() -> None:
    service, _ = make_import_service(contract=CONTRACT, now=NOW)
    with pytest.raises(IngestionTransientError):
        service.process(uuid4())


def test_process_marks_run_failed_with_actionable_code() -> None:
    from umbral.application.ingestion.contracts import ParsedBatch

    class FlakySource:
        def __init__(self) -> None:
            self.calls = 0

        def read_batch(self, **kwargs: object) -> ParsedBatch:
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("boom")
            return ParsedBatch(records=(), parse_errors=())

    service, runs = make_import_service(
        contract=CONTRACT, now=NOW, source=FlakySource()
    )
    service.submit(_request(file_name="flaky.json", raw=b"{}"))
    execution_id = _execution(service)

    with pytest.raises(Exception):
        service.process(execution_id)
    run = runs.get_by_identity("source-a", "batch-key-1")
    assert run is not None
    assert run.state == "failed"
    assert run.error_code is not None
    assert run.error_detail


def _execution(service: ImportRunService) -> UUID:
    runtime = service.job_runtime
    assert isinstance(runtime, InMemoryJobRuntime)
    return runtime.submissions[-1].execution_id
