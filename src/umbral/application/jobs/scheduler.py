"""Simple UTC one-shot/fixed-interval scheduler."""

from __future__ import annotations

from datetime import datetime, timezone

from .service import InMemoryJobRuntime


class InMemoryScheduler:
    def __init__(self, runtime: InMemoryJobRuntime, *, scheduler_id: str) -> None:
        self.runtime = runtime
        self.scheduler_id = scheduler_id
        self.last_heartbeat: datetime | None = None

    def tick(self) -> int:
        self.last_heartbeat = datetime.now(timezone.utc)
        return self.runtime.schedule_tick()
