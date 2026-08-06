"""Orchestration for controlled Bronze ingestion.

The service owns run state transitions, idempotent capture and derived counts.
Repositories manage their own persistence (session-per-operation in production,
in-memory in tests) so an interrupted attempt can be replayed safely: identical
records are skipped by the ``(source_id, external_id, content_sha256)`` guard.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime, timezone
from io import BytesIO
from typing import Callable
from uuid import UUID, uuid4

from umbral.application.ingestion.contracts import (
    BatchRejected,
    ImportBatchRequest,
    ImportRun,
    ImportRunSnapshot,
    IngestionPermanentError,
    IngestionTransientError,
    QualityReport,
    QuarantineRecord,
    RawListingSnapshot,
    raw_content_type,
)
from umbral.application.ingestion.import_contract import (
    ContractSpec,
    canonical_hash,
    check_file,
    validate_record,
)
from umbral.application.ingestion.ports import (
    ImportRunRepository,
    ImportSource,
    QuarantineRepository,
    RawSnapshotRepository,
)
from umbral.application.jobs.contracts import SubmitJob
from umbral.application.jobs.ports import JobRuntime
from umbral.application.objects.contracts import (
    ObjectIntegrityError,
    ObjectNotFound,
    ObjectStateError,
    ProviderObjectRef,
)
from umbral.application.objects.ports import ObjectStore

IMPORT_JOB_TYPE = "ingestion.import_batch"
_RAW_KEY_PREFIX = "ingestion/raw"
_DETAIL_BOUND = 500

Clock = Callable[[], datetime]


def raw_storage_key(file_sha256: str) -> str:
    return f"{_RAW_KEY_PREFIX}/{file_sha256}"


class ImportRunService:
    def __init__(
        self,
        *,
        runs: ImportRunRepository,
        snapshots: RawSnapshotRepository,
        quarantine: QuarantineRepository,
        source: ImportSource,
        contract: ContractSpec,
        objects: ObjectStore,
        job_runtime: JobRuntime | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.runs = runs
        self.snapshots = snapshots
        self.quarantine = quarantine
        self.source = source
        self.contract = contract
        self.objects = objects
        self.job_runtime = job_runtime
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def submit(self, request: ImportBatchRequest) -> ImportRunSnapshot:
        existing = self.runs.get_by_identity(
            request.source.source_id, request.batch_key
        )
        if existing is not None:
            return existing.snapshot()

        check = check_file(
            self.contract,
            raw=request.raw,
            file_format=request.file_format,
            declared_contract_version=request.source.contract_version,
        )
        if not check.valid:
            raise BatchRejected(
                check.code or "file.invalid", check.detail or "batch rejected"
            )
        parsed = self.source.read_batch(
            raw=request.raw,
            file_format=request.file_format,
            file_name=request.file_name,
        )
        if parsed.total > self.contract.file.max_records:
            raise BatchRejected(
                "file.records_exceeded",
                f"batch exceeds {self.contract.file.max_records} records",
            )

        file_sha256 = hashlib.sha256(request.raw).hexdigest()
        storage_key = raw_storage_key(file_sha256)
        self.objects.put_if_absent(
            storage_key=storage_key,
            body=BytesIO(request.raw),
            sha256=file_sha256,
            size_bytes=len(request.raw),
            content_type=raw_content_type(request.file_format),
        )
        job = None
        if self.job_runtime is not None:
            job = self.job_runtime.submit(
                SubmitJob.create(
                    job_type=IMPORT_JOB_TYPE,
                    logical_target=_job_target(request),
                    idempotency_key=request.batch_key,
                    correlation_id=request.correlation_id,
                    actor=request.actor,
                )
            )
        run = self.runs.create(
            run_id=uuid4(),
            source=request.source,
            batch_key=request.batch_key,
            file_format=request.file_format,
            file_name=request.file_name,
            file_sha256=file_sha256,
            file_size_bytes=len(request.raw),
            raw_storage_key=storage_key,
            job_execution_id=job.execution_id if job is not None else None,
            correlation_id=request.correlation_id,
            actor_kind=request.actor.kind,
            actor_id=request.actor.id,
            now=self.clock(),
        )
        return run.snapshot()

    def get(self, run_id: UUID) -> ImportRunSnapshot:
        run = self._require_run(run_id)
        return run.snapshot()

    def quality(self, run_id: UUID) -> QualityReport:
        from umbral.application.ingestion.contracts import RunNotTerminalError
        from umbral.application.ingestion.quality import build_quality_report

        run = self._require_run(run_id)
        if run.state != "succeeded":
            raise RunNotTerminalError(run_id)
        snapshots = self.snapshots.list_for_run(run_id)
        return build_quality_report(
            run_id=run_id,
            counts=run.counts,
            snapshot_payloads=[snapshot.payload for snapshot in snapshots],
            contract=self.contract,
        )

    def quarantine_records(self, run_id: UUID) -> tuple[QuarantineRecord, ...]:
        self._require_run(run_id)
        return self.quarantine.list_for_run(run_id)

    def quarantine_record(self, record_id: UUID) -> QuarantineRecord | None:
        return self.quarantine.get(record_id)

    def process(self, execution_id: UUID) -> ImportRunSnapshot:
        """Capture one run; the durable job handler calls this by execution id."""
        run = self.runs.find_by_job_execution(execution_id)
        if run is None:
            raise IngestionTransientError(
                "ingestion.run_not_ready", "run is not yet linked to this execution"
            )
        if run.state in {"succeeded", "failed"}:
            return run.snapshot()
        run.state = "running"
        run.updated_at = self.clock()
        self.runs.save(run)
        try:
            return self._capture(run)
        except IngestionTransientError:
            raise
        except Exception as error:
            code = getattr(error, "code", "ingestion.processing_failed")
            detail = _bounded(
                getattr(error, "detail", None) or str(error) or "processing failed"
            )
            self._fail(run, code=code, detail=detail)
            raise IngestionPermanentError(code, detail) from error

    def _capture(self, run: ImportRun) -> ImportRunSnapshot:
        provider_ref = ProviderObjectRef(run.raw_storage_key)
        try:
            info = self.objects.stat(provider_ref)
            if info.sha256 != run.file_sha256 or info.size_bytes != run.file_size_bytes:
                raise IngestionPermanentError(
                    "object.integrity_error",
                    "raw batch object integrity does not match",
                )
            raw = self.objects.open(provider_ref).read()
        except (ObjectNotFound, ObjectStateError) as error:
            raise IngestionTransientError(
                "ingestion.raw_unavailable", "raw batch object is not available yet"
            ) from error
        except ObjectIntegrityError as error:
            raise IngestionPermanentError(
                "object.integrity_error", "raw batch object integrity is broken"
            ) from error
        parsed = self.source.read_batch(
            raw=raw, file_format=run.file_format, file_name=run.file_name
        )
        if parsed.total > self.contract.file.max_records:
            raise IngestionPermanentError(
                "file.records_exceeded",
                f"batch exceeds {self.contract.file.max_records} records",
            )

        captured_at = self.clock()
        seen: set[tuple[str, str]] = set()
        accepted = 0
        quarantined = 0
        duplicates = 0
        missing_total = 0
        for index, record in enumerate(parsed.records):
            external_id = _external_id(record.payload, index)
            content_sha256 = canonical_hash(record.payload)
            key = (external_id, content_sha256)
            if key in seen:
                duplicates += 1
                continue
            if self.snapshots.exists(
                source_id=run.source.source_id,
                external_id=external_id,
                content_sha256=content_sha256,
            ):
                duplicates += 1
                continue
            result = validate_record(record.payload, self.contract)
            if not result.valid:
                self.quarantine.insert(
                    QuarantineRecord(
                        record_id=uuid4(),
                        run_id=run.run_id,
                        source=run.source,
                        external_id=external_id,
                        code=result.issues[0].code,
                        rule=result.issues[0].rule,
                        detail=_bounded(
                            "; ".join(issue.detail for issue in result.issues)
                        ),
                        payload=record.payload,
                        created_at=captured_at,
                    )
                )
                quarantined += 1
            else:
                self.snapshots.insert(
                    RawListingSnapshot(
                        snapshot_id=uuid4(),
                        run_id=run.run_id,
                        source=run.source,
                        external_id=external_id,
                        payload=record.payload,
                        content_sha256=content_sha256,
                        content_type="application/json",
                        size_bytes=len(record.raw_bytes),
                        published_at=_parse_published_at(record.payload),
                        captured_at=captured_at,
                    )
                )
                accepted += 1
                missing_total += result.missing_optional
                seen.add(key)
        for parse_error in parsed.parse_errors:
            self.quarantine.insert(
                QuarantineRecord(
                    record_id=uuid4(),
                    run_id=run.run_id,
                    source=run.source,
                    external_id=None,
                    code=parse_error.code,
                    rule="source.parse",
                    detail=_bounded(parse_error.detail),
                    payload=None,
                    created_at=captured_at,
                )
            )
            quarantined += 1

        run.total_records = parsed.total
        run.accepted = accepted
        run.quarantined = quarantined
        run.duplicates = duplicates
        run.missing_fields = missing_total
        run.state = "succeeded"
        run.finished_at = captured_at
        run.updated_at = captured_at
        run.error_code = None
        run.error_detail = None
        self.runs.save(run)
        return run.snapshot()

    def _fail(self, run: ImportRun, *, code: str, detail: str) -> None:
        now = self.clock()
        run.state = "failed"
        run.finished_at = now
        run.updated_at = now
        run.error_code = _normalized_code(code)
        run.error_detail = _bounded(detail)
        self.runs.save(run)

    def _require_run(self, run_id: UUID) -> ImportRun:
        run = self.runs.get(run_id)
        if run is None:
            from umbral.application.ingestion.contracts import ImportRunNotFound

            raise ImportRunNotFound(run_id)
        return run


def _external_id(payload: Mapping[str, object], index: int) -> str:
    value = payload.get("external_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return f"record:{index}"


def _parse_published_at(payload: Mapping[str, object]) -> datetime | None:
    value = payload.get("published_at")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _job_target(request: ImportBatchRequest) -> str:
    target = f"{request.source.source_id}:{request.batch_key}"
    return target[:280]


def _normalized_code(value: str) -> str:
    candidate = value.strip().lower().replace(" ", "_")
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789._-"
    if not candidate or any(char not in allowed for char in candidate):
        return "ingestion.processing_failed"
    return candidate[:100]


def _bounded(value: str, bound: int = _DETAIL_BOUND) -> str:
    return value[:bound]
