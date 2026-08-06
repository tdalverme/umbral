"""Durable handler that normalizes one import run into Silver in the worker."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from uuid import UUID, uuid4

from umbral.application.ingestion.contracts import ImportRunSnapshot
from umbral.application.jobs.contracts import (
    JobContext,
    JsonScalar,
    PermanentJobError,
    SubmitJob,
    TransientJobError,
    normalize_target,
)
from umbral.application.jobs.ports import JobRuntime
from umbral.application.silver.contracts import (
    SilverPermanentError,
    SilverTransientError,
)
from umbral.application.silver.service import (
    SILVER_NORMALIZE_JOB_TYPE,
    NormalizeRunService,
)
from umbral.domain.audit import AuditActor
from umbral.workers.registry import JobRegistry

NormalizePublisher = Callable[[ImportRunSnapshot], None]


def normalize_publisher(runtime: JobRuntime) -> NormalizePublisher:
    """Chain a normalize job per succeeded import run, idempotent by identity."""

    def publish(snapshot: ImportRunSnapshot) -> None:
        runtime.submit(
            SubmitJob.create(
                job_type=SILVER_NORMALIZE_JOB_TYPE,
                logical_target=str(snapshot.run_id),
                idempotency_key=f"normalize:{snapshot.run_id}",
                correlation_id=uuid4(),
                actor=AuditActor.system(),
            )
        )

    return publish


class SilverNormalizeHandler:
    job_type = SILVER_NORMALIZE_JOB_TYPE

    def __init__(self, service: NormalizeRunService) -> None:
        self.service = service

    def normalize_target(self, raw_target: str) -> str:
        return normalize_target(raw_target)

    def run(self, context: JobContext) -> Mapping[str, JsonScalar]:
        if context.logical_target is None:
            raise PermanentJobError("silver.target_missing")
        try:
            run_id = UUID(context.logical_target)
        except ValueError:
            raise PermanentJobError("silver.target_invalid") from None
        try:
            summary = self.service.process(run_id)
        except SilverTransientError as error:
            raise TransientJobError(error.code) from error
        except SilverPermanentError as error:
            raise PermanentJobError(error.code) from error
        return {
            "run_id": str(summary.run_id),
            "total_snapshots": summary.total_snapshots,
            "listings_inserted": summary.listings_inserted,
            "skipped": summary.skipped,
            "changes_emitted": summary.changes_emitted,
            "links_created": summary.links_created,
            "proposals_created": summary.proposals_created,
        }


def build_silver_registry(service: NormalizeRunService) -> JobRegistry:
    handler = SilverNormalizeHandler(service)
    return JobRegistry({handler.job_type: handler})
