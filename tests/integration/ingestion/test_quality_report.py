"""US3 quality: exact counts, missing fields, abnormal signals and download."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import pytest
from tests.fakes.imports import make_import_service

from umbral.application.ingestion.contracts import (
    ImportBatchRequest,
    RunNotTerminalError,
    SourceIdentity,
)
from umbral.application.ingestion.service import ImportRunService
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.domain.audit import AuditActor
from umbral.infrastructure.ingestion.contract_loader import load_contract_v1

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures" / "imports"
CONTRACT = load_contract_v1()
NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _request(
    batch_key: str = "q-key", file_format: Literal["csv", "json"] = "json"
) -> ImportBatchRequest:
    return ImportBatchRequest(
        source=SourceIdentity("source-a", "v1", "1"),
        batch_key=batch_key,
        file_format="json",
        file_name="reference-batch.json",
        raw=(FIXTURES / "reference-batch.json").read_bytes(),
        actor=AuditActor(kind="operator", id="operator-1"),
        correlation_id=uuid4(),
    )


def _run_id(service: ImportRunService) -> UUID:
    runtime = service.job_runtime
    assert isinstance(runtime, InMemoryJobRuntime)
    run = service.runs.find_by_job_execution(runtime.submissions[-1].execution_id)
    assert run is not None
    return run.run_id


def _succeeded_service() -> ImportRunService:
    service, _ = make_import_service(contract=CONTRACT, now=NOW)
    service.submit(_request())
    runtime = service.job_runtime
    assert isinstance(runtime, InMemoryJobRuntime)
    service.process(runtime.submissions[-1].execution_id)
    return service


def test_quality_report_counts_match_committed_rows() -> None:
    service = _succeeded_service()
    run = service.get(_run_id(service))
    report = service.quality(run.run_id)

    assert run.state == "succeeded"
    assert report.counts.total_records == 12
    assert report.counts.accepted == 9
    assert report.counts.quarantined == 2
    assert report.counts.duplicates == 1
    assert report.counts.missing_fields == 3
    assert report.missing_fields_by_name == {
        "neighborhood": 1,
        "expenses": 1,
        "published_at": 1,
    }
    assert len(report.abnormal_distributions) >= 1


def test_quality_rejects_non_terminal_run() -> None:
    service, _ = make_import_service(contract=CONTRACT, now=NOW)
    snapshot = service.submit(_request("pending-key"))
    with pytest.raises(RunNotTerminalError):
        service.quality(snapshot.run_id)


def test_quarantine_records_are_consultable_with_detail() -> None:
    service = _succeeded_service()
    records = service.quarantine_records(_run_id(service))
    assert len(records) == 2
    codes = sorted(record.code for record in records)
    assert codes == ["contract.enum_invalid", "contract.range_invalid"]
    for record in records:
        assert record.detail
        assert record.external_id is not None


def test_quality_and_download_via_api() -> None:
    from datetime import datetime as _dt
    from datetime import timezone as _tz
    from uuid import uuid4 as _uuid4

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tests.fakes.imports import make_import_service as _make

    from umbral.api.dependencies import RuntimeDependencies as _Deps
    from umbral.api.routers.imports import configure_imports_routes, router
    from umbral.application.identity.contracts import CurrentPrincipal
    from umbral.infrastructure.config.settings import Settings

    service, _ = _make(contract=CONTRACT, now=NOW)

    class FakeAccess:
        def authorize(
            self,
            token: str,
            *,
            action: str,
            resource_owner_id: object,
            now: _dt,
            correlation_id: object = None,
        ) -> CurrentPrincipal:
            return CurrentPrincipal(
                _uuid4(), ("operator",), _dt(2026, 8, 1, tzinfo=_tz.utc)
            )

    deps = _Deps(
        settings=Settings.from_environment(
            {
                "UMBRAL_ENV": "local",
                "UMBRAL_RELEASE_ID": "foundation-local",
                "UMBRAL_RELEASE_MANIFEST": "<local>",
                "DATABASE_URL": "postgresql://umbral:local@127.0.0.1/umbral",
                "REDIS_URL": "redis://127.0.0.1:6379/0",
                "OBJECT_STORE_BACKEND": "filesystem",
                "OBJECT_STORE_ROOT": ".umbral-local",
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
                "UMBRAL_API_BASE_URL": "http://127.0.0.1:8000",
                "SESSION_COOKIE_NAME": "umbral_test_session",
                "SESSION_SECURE": "false",
            }
        ),
        release=None,  # type: ignore[arg-type]
        readiness=None,  # type: ignore[arg-type]
        object_store=None,  # type: ignore[arg-type]
        identity_store=None,  # type: ignore[arg-type]
        identity_access=None,  # type: ignore[arg-type]
        access_control=FakeAccess(),  # type: ignore[arg-type]
        administration=None,  # type: ignore[arg-type]
        ingestion=service,
    )
    app = FastAPI()
    configure_imports_routes(deps)
    app.include_router(router)
    client = TestClient(app)

    submitted = client.post(
        "/api/v1/imports/batches",
        cookies={"umbral_test_session": "token"},
        files={
            "file": (
                "reference-batch.json",
                (FIXTURES / "reference-batch.json").read_bytes(),
                "application/json",
            )
        },
        data={"source_id": "source-a", "source_version": "v1", "contract_version": "1"},
    )
    run_id = submitted.json()["run_id"]

    pending = client.get(
        f"/api/v1/imports/runs/{run_id}/quality",
        cookies={"umbral_test_session": "token"},
    )
    assert pending.status_code == 409

    from umbral.application.jobs.service import InMemoryJobRuntime

    runtime = service.job_runtime
    assert isinstance(runtime, InMemoryJobRuntime)
    service.process(runtime.submissions[-1].execution_id)

    quality = client.get(
        f"/api/v1/imports/runs/{run_id}/quality",
        cookies={"umbral_test_session": "token"},
    )
    assert quality.status_code == 200
    body = quality.json()
    assert body["counts"]["accepted"] == 9
    assert body["counts"]["quarantined"] == 2
    assert body["counts"]["duplicates"] == 1
    assert body["missing_fields_by_name"] == {
        "neighborhood": 1,
        "expenses": 1,
        "published_at": 1,
    }

    download = client.get(
        f"/api/v1/imports/runs/{run_id}/quality/download",
        cookies={"umbral_test_session": "token"},
    )
    assert download.status_code == 200
    assert "text/csv" in download.headers["content-type"]
    assert "contract.range_invalid" in download.text
    assert "contract.enum_invalid" in download.text
