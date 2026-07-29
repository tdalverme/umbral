"""Worker-process scheduler loop with bounded heartbeat cadence."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from threading import Event

from umbral.application.jobs.scheduler import InMemoryScheduler

HEARTBEAT_INTERVAL_SECONDS = 30


def run_scheduler(
    scheduler: InMemoryScheduler,
    *,
    stop: Event,
    sleep: Callable[[float], None],
) -> None:
    """Run one bounded scheduler tick every <=30 seconds until stopped."""

    while not stop.is_set():
        scheduler.tick()
        sleep(HEARTBEAT_INTERVAL_SECONDS)


def heartbeat_now() -> datetime:
    return datetime.now(timezone.utc)
