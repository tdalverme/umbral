"""Durable handlers: SilverNormalizeHandler and the chained normalize publish."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from tests.fakes.imports import (
    InMemoryImportRunRepository,
    InMemoryRawSnapshotRepository,
)
from tests.fakes.silver import make_normalize_service
from tests.support.silver import (
    build_run,
    load_records,
    snapshot_from_payload,
    store_succeeded_run,
)

from umbral.application.ingestion.contracts import ImportRun
from umbral.application.jobs.contracts import (
    JobContext,
    PermanentJobError,
    TransientJobError,
)
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.application.silver.service import (
    SILVER_NORMALIZE_JOB_TYPE,
    NormalizeRunService,
)
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.infrastructure.silver.contract_loader import (
    load_dedupe_policy,
    load_silver_schema,
)
from umbral.workers.silver import SilverNormalizeHandler, normalize_publisher

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _service() -> tuple[NormalizeRunService, ImportRun]:
    schema = load_silver_schema()
    dedupe = load_dedupe_policy()
    snapshots = InMemoryRawSnapshotRepository()
    runs = InMemoryImportRunRepository()
    run = build_run()
    store_succeeded_run(runs, run)
    records = [
        r
        for r in load_records("reference-batch.json")
        if str(r["external_id"]).startswith("sil-000")
    ]
    for record in records:
        snapshots.insert(
            snapshot_from_payload(
                record, run_id=run.run_id, source_id="source-a", captured_at=NOW
            )
        )
    service = make_normalize_service(
        snapshots=snapshots, runs=runs, schema=schema, dedupe=dedupe, now=NOW
    )
    return service, run


def _context(logical_target: str) -> JobContext:
    return JobContext(
        execution_id=uuid4(),
        attempt_number=1,
        correlation_id=uuid4(),
        release_id="foundation-local",
        logical_target=logical_target,
    )


def test_silver_handler_returns_bounded_summary() -> None:
    service, run = _service()
    handler = SilverNormalizeHandler(service)
    result = handler.run(_context(str(run.run_id)))
    assert result["listings_inserted"] == 9
    assert result["total_snapshots"] == 9
    # sil-0001 and sil-0002 share identical strong fields -> deterministic link.
    assert result["links_created"] == 1


def test_silver_handler_rejects_invalid_target() -> None:
    service, _ = _service()
    handler = SilverNormalizeHandler(service)
    with pytest.raises(PermanentJobError) as raised:
        handler.run(_context("not-a-uuid"))
    assert raised.value.code == "silver.target_invalid"


def test_silver_handler_maps_transient_errors() -> None:
    service, _ = _service()
    handler = SilverNormalizeHandler(service)
    with pytest.raises(TransientJobError) as raised:
        handler.run(_context(str(UUID(int=999))))
    assert raised.value.code == "silver.run_not_ready"


def test_normalize_publisher_submits_idempotent_job() -> None:
    _, run = _service()
    runtime = InMemoryJobRuntime(queue=RecordingJobQueue())
    publisher = normalize_publisher(runtime)
    snapshot = run.snapshot()
    publisher(snapshot)
    publisher(snapshot)
    assert len(runtime.submissions) == 1
    assert runtime.submissions[0].identity.job_type == SILVER_NORMALIZE_JOB_TYPE
    assert runtime.submissions[0].identity.idempotency_key == f"normalize:{run.run_id}"
