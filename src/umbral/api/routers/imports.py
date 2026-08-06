"""Operator entry for controlled Bronze ingestion (H2.1)."""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, Header, Request, Response, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.application.ingestion.contracts import (
    BatchRejected,
    ImportBatchRequest,
    ImportRunSnapshot,
    IngestionError,
    QualityReport,
    QuarantineRecord,
    SourceIdentity,
)
from umbral.domain.audit import AuditActor

router = APIRouter(prefix="/api/v1", tags=["Imports"])
_dependencies: RuntimeDependencies | None = None

RunState = Literal["pending", "running", "succeeded", "failed"]


class RunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: UUID
    source_id: str
    source_version: str
    contract_version: str
    batch_key: str
    file_format: Literal["csv", "json"]
    file_name: str
    file_sha256: str
    state: RunState
    created_at: datetime
    finished_at: datetime | None = None
    total_records: int = 0
    accepted: int = 0
    quarantined: int = 0
    duplicates: int = 0
    missing_fields: int = 0
    error_code: str | None = None
    error_detail: str | None = None

    @classmethod
    def from_snapshot(cls, snapshot: ImportRunSnapshot) -> "RunResponse":
        return cls(
            run_id=snapshot.run_id,
            source_id=snapshot.source.source_id,
            source_version=snapshot.source.source_version,
            contract_version=snapshot.source.contract_version,
            batch_key=snapshot.batch_key,
            file_format=snapshot.file_format,
            file_name=snapshot.file_name,
            file_sha256=snapshot.file_sha256,
            state=snapshot.state,
            created_at=snapshot.created_at,
            finished_at=snapshot.finished_at,
            total_records=snapshot.total_records,
            accepted=snapshot.accepted,
            quarantined=snapshot.quarantined,
            duplicates=snapshot.duplicates,
            missing_fields=snapshot.missing_fields,
            error_code=snapshot.error_code,
            error_detail=snapshot.error_detail,
        )


class RunCountsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total: int
    accepted: int
    quarantined: int
    duplicates: int
    missing_fields: int


class AbnormalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str
    signal: str
    detail: str


class QualityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: UUID
    counts: RunCountsModel
    missing_fields_by_name: dict[str, int]
    abnormal_distributions: list[AbnormalModel]


class QuarantineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    record_id: UUID
    run_id: UUID
    source_id: str
    external_id: str | None = None
    code: str
    rule: str
    detail: str
    created_at: datetime

    @classmethod
    def from_record(cls, record: QuarantineRecord) -> "QuarantineResponse":
        return cls(
            record_id=record.record_id,
            run_id=record.run_id,
            source_id=record.source.source_id,
            external_id=record.external_id,
            code=record.code,
            rule=record.rule,
            detail=record.detail,
            created_at=record.created_at,
        )


def configure_imports_routes(dependencies: RuntimeDependencies) -> None:
    global _dependencies
    _dependencies = dependencies


def _deps() -> RuntimeDependencies:
    if _dependencies is None:
        raise RuntimeError("imports routes were not configured")
    return _dependencies


def _problem(request: Request, status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": f"https://umbral.invalid/problems/{code}",
            "title": "Importacion rechazada",
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID", str(uuid4())),
            "correlation_id": request.headers.get("X-Correlation-ID", str(uuid4())),
        },
        headers={"Cache-Control": "no-store"},
    )


def _authorize(request: Request, action: str) -> CurrentPrincipal:
    token = request.cookies.get(_deps().settings.session_cookie_name)
    if not token:
        raise IdentityError("auth.session_required", status=401, recovery="sign_in")
    correlation = _correlation(request)
    return _deps().access_control.authorize(
        token,
        action=action,
        resource_owner_id=None,
        now=datetime.now(timezone.utc),
        correlation_id=correlation,
    )


def _correlation(request: Request) -> UUID | None:
    value = request.headers.get("X-Correlation-ID")
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _detect_format(file_name: str | None) -> Literal["csv", "json"]:
    if not file_name or "." not in file_name:
        return "json"
    extension = file_name.rsplit(".", 1)[-1].lower()
    if extension == "csv":
        return "csv"
    if extension == "json":
        return "json"
    raise BatchRejected(
        "file.format_unsupported", "file extension must be .csv or .json"
    )


@router.post(
    "/imports/batches",
    operation_id="submitImportBatch",
    status_code=202,
    response_model=RunResponse,
    responses={
        400: {"description": "Batch rejected by the import contract"},
        401: {"description": "Missing or invalid session"},
        403: {"description": "Operator role required"},
    },
)
async def submit_batch(
    request: Request,
    file: UploadFile = File(...),
    source_id: str = Form(...),
    source_version: str = Form(...),
    contract_version: str = Form(...),
    batch_key: str | None = Form(default=None),
    x_correlation_id: UUID | None = Header(default=None),
) -> RunResponse | JSONResponse:
    try:
        principal = _authorize(request, "ops.ingestion.batch.submit")
        raw = await file.read()
        file_format = _detect_format(file.filename)
        key = batch_key or hashlib.sha256(raw).hexdigest()
        snapshot = _deps().ingestion.submit(
            ImportBatchRequest(
                source=SourceIdentity(source_id, source_version, contract_version),
                batch_key=key,
                file_format=file_format,
                file_name=file.filename or "upload",
                raw=raw,
                actor=AuditActor(kind="operator", id=str(principal.user_id)),
                correlation_id=x_correlation_id or uuid4(),
            )
        )
        return RunResponse.from_snapshot(snapshot)
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery)
    except BatchRejected as error:
        return _problem(request, 400, error.code, error.detail)
    except ValueError as error:
        return _problem(request, 400, "request.invalid", str(error))


@router.get(
    "/imports/runs/{run_id}",
    operation_id="getImportRun",
    response_model=RunResponse,
    responses={
        401: {"description": "Missing or invalid session"},
        403: {"description": "Operator role required"},
        404: {"description": "Unknown run"},
    },
)
async def get_import_run(
    run_id: UUID,
    request: Request,
    x_correlation_id: UUID | None = Header(default=None),
) -> RunResponse | JSONResponse:
    try:
        _authorize(request, "ops.ingestion.run.read")
        snapshot = _deps().ingestion.get(run_id)
        return RunResponse.from_snapshot(snapshot)
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery)
    except IngestionError as error:
        return _problem(request, 404, error.code, "run not found")


@router.get(
    "/imports/runs/{run_id}/quality",
    operation_id="getImportQuality",
    response_model=QualityResponse,
    responses={
        401: {"description": "Missing or invalid session"},
        403: {"description": "Operator role required"},
        404: {"description": "Unknown run"},
        409: {"description": "Run not in a terminal state"},
    },
)
async def get_import_quality(
    run_id: UUID,
    request: Request,
    x_correlation_id: UUID | None = Header(default=None),
) -> QualityResponse | JSONResponse:
    try:
        _authorize(request, "ops.ingestion.quality.read")
        report = _deps().ingestion.quality(run_id)
        return _quality_response(report)
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery)
    except IngestionError as error:
        status = 409 if error.code == "ingestion.run_not_terminal" else 404
        return _problem(request, status, error.code, "run unavailable")


@router.get(
    "/imports/runs/{run_id}/quality/download",
    operation_id="downloadImportQuality",
    response_model=None,
    response_class=PlainTextResponse,
    responses={
        401: {"description": "Missing or invalid session"},
        403: {"description": "Operator role required"},
        404: {"description": "Unknown run"},
    },
)
async def download_import_quality(
    run_id: UUID,
    request: Request,
    x_correlation_id: UUID | None = Header(default=None),
) -> Response | JSONResponse:
    try:
        _authorize(request, "ops.ingestion.quality.read")
        records = _deps().ingestion.quarantine_records(run_id)
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery)
    except IngestionError as error:
        return _problem(request, 404, error.code, "run not found")

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["run_id", "source_id", "external_id", "code", "rule", "detail"])
    for record in records:
        writer.writerow(
            [
                str(record.run_id),
                record.source.source_id,
                record.external_id or "",
                record.code,
                record.rule,
                record.detail,
            ]
        )
    return Response(
        content=buffer.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/imports/quarantine/{record_id}",
    operation_id="getQuarantineRecord",
    response_model=QuarantineResponse,
    responses={
        401: {"description": "Missing or invalid session"},
        403: {"description": "Operator role required"},
        404: {"description": "Unknown record"},
    },
)
async def get_quarantine_record(
    record_id: UUID,
    request: Request,
    x_correlation_id: UUID | None = Header(default=None),
) -> QuarantineResponse | JSONResponse:
    try:
        _authorize(request, "ops.ingestion.run.read")
        record = _deps().ingestion.quarantine_record(record_id)
        if record is None:
            return _problem(
                request, 404, "ingestion.record_not_found", "record not found"
            )
        return QuarantineResponse.from_record(record)
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery)


def _quality_response(report: QualityReport) -> QualityResponse:
    return QualityResponse(
        run_id=report.run_id,
        counts=RunCountsModel(
            total=report.counts.total_records,
            accepted=report.counts.accepted,
            quarantined=report.counts.quarantined,
            duplicates=report.counts.duplicates,
            missing_fields=report.counts.missing_fields,
        ),
        missing_fields_by_name=dict(report.missing_fields_by_name),
        abnormal_distributions=[
            AbnormalModel(field=item.field, signal=item.signal, detail=item.detail)
            for item in report.abnormal_distributions
        ],
    )

