"""Durable handler that computes and publishes one recommendation run in the worker."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from umbral.application.jobs.contracts import (
    JobContext,
    JsonScalar,
    PermanentJobError,
    TransientJobError,
    normalize_target,
)
from umbral.application.radar.contracts import (
    RadarPermanentError,
    RadarTransientError,
)
from umbral.application.radar.service import RADAR_RUN_JOB_TYPE, RadarService
from umbral.workers.registry import JobRegistry


class RecommendationRunHandler:
    job_type = RADAR_RUN_JOB_TYPE

    def __init__(self, service: RadarService) -> None:
        self.service = service

    def normalize_target(self, raw_target: str) -> str:
        return normalize_target(raw_target)

    def run(self, context: JobContext) -> Mapping[str, JsonScalar]:
        if context.logical_target is None:
            raise PermanentJobError("radar.target_missing")
        try:
            run_id = UUID(context.logical_target)
        except ValueError:
            raise PermanentJobError("radar.target_invalid") from None
        try:
            summary = self.service.process_run(
                run_id=run_id,
                job_execution_id=context.execution_id,
            )
        except RadarTransientError as error:
            raise TransientJobError(error.code) from error
        except RadarPermanentError as error:
            raise PermanentJobError(error.code) from error
        return {
            "run_id": str(summary["run_id"]),
            "state": str(summary["state"]),
            "candidate_count": _int(summary["candidate_count"]),
            "published_item_count": _int(summary["published_item_count"]),
            "failure_code": (
                str(summary["failure_code"])
                if summary["failure_code"] is not None
                else None
            ),
            "score_policy_version": str(summary["score_policy_version"]),
        }


def _int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def build_radar_registry(service: RadarService) -> JobRegistry:
    handler = RecommendationRunHandler(service)
    return JobRegistry({handler.job_type: handler})
