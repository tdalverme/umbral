"""Durable handler that captures one import run in the worker process."""

from __future__ import annotations

from collections.abc import Mapping

from umbral.application.ingestion.contracts import (
    IngestionPermanentError,
    IngestionTransientError,
)
from umbral.application.ingestion.service import IMPORT_JOB_TYPE, ImportRunService
from umbral.application.jobs.contracts import (
    JobContext,
    JsonScalar,
    PermanentJobError,
    TransientJobError,
    normalize_target,
)
from umbral.workers.registry import JobRegistry


class IngestionImportHandler:
    job_type = IMPORT_JOB_TYPE

    def __init__(self, service: ImportRunService) -> None:
        self.service = service

    def normalize_target(self, raw_target: str) -> str:
        return normalize_target(raw_target)

    def run(self, context: JobContext) -> Mapping[str, JsonScalar]:
        try:
            snapshot = self.service.process(context.execution_id)
        except IngestionTransientError as error:
            raise TransientJobError(error.code) from error
        except IngestionPermanentError as error:
            raise PermanentJobError(error.code) from error
        return {
            "run_id": str(snapshot.run_id),
            "state": snapshot.state,
            "total_records": snapshot.total_records,
            "accepted": snapshot.accepted,
            "quarantined": snapshot.quarantined,
            "duplicates": snapshot.duplicates,
            "missing_fields": snapshot.missing_fields,
        }


def build_ingestion_registry(service: ImportRunService) -> JobRegistry:
    handler = IngestionImportHandler(service)
    registry = JobRegistry({handler.job_type: handler})
    return registry
