"""Outbox relay and lease reaper application services."""

from __future__ import annotations

from dataclasses import dataclass

from umbral.application.jobs.ports import JobQueue, JobRuntime, RelayResult


class JobOutboxRelay:
    def __init__(self, runtime: JobRuntime, queue: JobQueue) -> None:
        self.runtime = runtime
        self.queue = queue

    def publish_due(self, *, limit: int = 100) -> RelayResult:
        return self.runtime.relay_due(queue=self.queue, limit=limit)

    def rebuild_after_transport_loss(self, *, limit: int = 100) -> RelayResult:
        self.runtime.rebuild_outbox(limit=limit)
        return self.publish_due(limit=limit)


@dataclass(frozen=True, slots=True)
class ReaperResult:
    abandoned: int


class JobLeaseReaper:
    def __init__(self, runtime: JobRuntime) -> None:
        self.runtime = runtime

    def reap(self) -> ReaperResult:
        return ReaperResult(abandoned=self.runtime.reap_expired())
