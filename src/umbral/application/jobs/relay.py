"""Outbox relay and lease reaper application services."""

from __future__ import annotations

from dataclasses import dataclass

from umbral.application.jobs.ports import JobQueue

from .service import InMemoryJobRuntime, RelayResult


class JobOutboxRelay:
    def __init__(self, runtime: InMemoryJobRuntime, queue: JobQueue) -> None:
        self.runtime = runtime
        self.queue = queue

    def publish_due(self, *, limit: int = 100) -> RelayResult:
        return self.runtime.relay_due(queue=self.queue, limit=limit)


@dataclass(frozen=True, slots=True)
class ReaperResult:
    abandoned: int


class JobLeaseReaper:
    def __init__(self, runtime: InMemoryJobRuntime) -> None:
        self.runtime = runtime

    def reap(self) -> ReaperResult:
        return ReaperResult(abandoned=self.runtime.reap_expired())
