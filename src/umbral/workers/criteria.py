"""Durable handlers for extraction batches and selective recomputes."""

from __future__ import annotations

from collections.abc import Mapping

from umbral.application.criteria.contracts import (
    CriteriaPermanentError,
    CriteriaTransientError,
    RecomputeScope,
)
from umbral.application.criteria.service import (
    EXTRACTION_RUN_JOB_TYPE,
    RECOMPUTE_JOB_TYPE,
    CriteriaService,
)
from umbral.application.jobs.contracts import (
    JobContext,
    JsonScalar,
    PermanentJobError,
    TransientJobError,
    normalize_target,
)
from umbral.application.jobs.ports import JobHandler
from umbral.workers.registry import JobRegistry


class ExtractionRunHandler:
    """Runs an extraction batch over a scope (``extraction.run``)."""

    job_type = EXTRACTION_RUN_JOB_TYPE

    def __init__(self, service: CriteriaService) -> None:
        self.service = service

    def normalize_target(self, raw_target: str) -> str:
        return normalize_target(raw_target)

    def run(self, context: JobContext) -> Mapping[str, JsonScalar]:
        if context.logical_target is None:
            raise PermanentJobError("criteria.target_missing")
        try:
            scope = RecomputeScope.parse(context.logical_target)
        except ValueError:
            raise PermanentJobError("criteria.target_invalid") from None
        try:
            summary = self.service.process_extraction(
                scope,
                job_execution_id=context.execution_id,
                correlation_id=context.correlation_id,
            )
        except CriteriaTransientError as error:
            raise TransientJobError(error.code) from error
        except CriteriaPermanentError as error:
            raise PermanentJobError(error.code) from error
        return _summary(summary)


class RecomputeHandler:
    """Runs a selective recompute over a scope (``extraction.recompute``)."""

    job_type = RECOMPUTE_JOB_TYPE

    def __init__(self, service: CriteriaService) -> None:
        self.service = service

    def normalize_target(self, raw_target: str) -> str:
        return normalize_target(raw_target)

    def run(self, context: JobContext) -> Mapping[str, JsonScalar]:
        if context.logical_target is None:
            raise PermanentJobError("criteria.target_missing")
        try:
            scope = RecomputeScope.parse(context.logical_target)
        except ValueError:
            raise PermanentJobError("criteria.target_invalid") from None
        cause = context.logical_target
        try:
            summary = self.service.process_recompute(
                scope,
                cause=cause,
                job_execution_id=context.execution_id,
                correlation_id=context.correlation_id,
            )
        except CriteriaTransientError as error:
            raise TransientJobError(error.code) from error
        except CriteriaPermanentError as error:
            raise PermanentJobError(error.code) from error
        return _summary(summary)


def _summary(summary: Mapping[str, object]) -> Mapping[str, JsonScalar]:
    return {
        key: (
            value
            if isinstance(value, (str, int, float, bool, type(None)))
            else str(value)
        )
        for key, value in summary.items()
    }


def build_criteria_registry(service: CriteriaService) -> JobRegistry:
    handlers: list[JobHandler] = [
        ExtractionRunHandler(service),
        RecomputeHandler(service),
    ]
    return JobRegistry({handler.job_type: handler for handler in handlers})
