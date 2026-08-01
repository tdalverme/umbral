"""Simple UTC one-shot/fixed-interval scheduler."""

from __future__ import annotations

from datetime import datetime, timezone

from umbral.application.runtime.telemetry import TelemetrySignal

from .ports import JobRuntime


class InMemoryScheduler:
    def __init__(self, runtime: JobRuntime, *, scheduler_id: str) -> None:
        self.runtime = runtime
        self.scheduler_id = scheduler_id
        self.last_heartbeat: datetime | None = None
        self.signals: list[TelemetrySignal] = []

    def tick(self) -> int:
        self.last_heartbeat = datetime.now(timezone.utc)
        scheduled = self.runtime.schedule_tick()
        self.signals.append(
            TelemetrySignal(
                correlation_id="00000000-0000-4000-8000-000000000000",
                service_name="scheduler",
                environment="local",
                release_id=self.runtime.release_id,
                operation="scheduler.tick",
                state="scheduled" if scheduled else "idle",
                duration_ms=0,
            )
        )
        return scheduled
