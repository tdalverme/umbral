"""Explicit job-handler registry; queue messages never choose imports dynamically."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from umbral.application.jobs.ports import JobHandler

if TYPE_CHECKING:
    from umbral.application.identity.access import IdentityAccess


def build_identity_registry(access: IdentityAccess) -> JobRegistry:
    """Compose the explicit identity issue handler without dynamic imports."""

    from umbral.workers.identity import (
        IdentityMagicLinkIssueHandler,
        IdentityRetentionHandler,
    )

    return JobRegistry(
        {
            "identity.magic_link.issue": IdentityMagicLinkIssueHandler(access),
            "identity.retention.purge": IdentityRetentionHandler(access),
        }
    )


class JobRegistry:
    def __init__(self, handlers: Mapping[str, JobHandler] | None = None) -> None:
        self._handlers: dict[str, JobHandler] = {}
        for handler in (handlers or {}).values():
            self.register(handler)

    def register(self, handler: JobHandler) -> None:
        job_type = handler.job_type.strip().lower()
        if not job_type or job_type != handler.job_type:
            raise ValueError("handler job_type must be canonical")
        if job_type in self._handlers:
            raise ValueError(f"job handler already registered: {job_type}")
        self._handlers[job_type] = handler

    def get(self, job_type: str) -> JobHandler | None:
        return self._handlers.get(job_type)

    def as_mapping(self) -> Mapping[str, JobHandler]:
        """Expose the immutable composition result to a job runtime."""

        return dict(self._handlers)

    def require(self, job_type: str) -> JobHandler:
        handler = self.get(job_type)
        if handler is None:
            raise KeyError(f"job handler is not registered: {job_type}")
        return handler

    def normalize_target(self, job_type: str, raw_target: str) -> str:
        return self.require(job_type).normalize_target(raw_target)

    def types(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))
