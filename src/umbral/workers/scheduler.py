"""Worker-process scheduler loop with bounded heartbeat cadence."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from threading import Event

from umbral.application.identity.ports import IdentityStore
from umbral.application.identity.retention import purge_request_fingerprints
from umbral.application.jobs.ports import JobQueue, JobRuntime
from umbral.application.jobs.scheduler import InMemoryScheduler

HEARTBEAT_INTERVAL_SECONDS = 30
DEFAULT_DUE_WORK_LIMIT = 100


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


def scheduler_once(
    runtime: JobRuntime,
    *,
    queue: JobQueue,
    identity_store: IdentityStore,
    limit: int = DEFAULT_DUE_WORK_LIMIT,
) -> dict[str, int]:
    """Run one durable cron pass in the required recovery-first order."""

    if not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    reclaimed_outbox = runtime.reclaim_expired_outbox(limit=limit)
    reaped_jobs = runtime.reap_expired(limit=limit)
    scheduled = 0
    while scheduled < limit:
        claimed = runtime.schedule_tick()
        if claimed == 0:
            break
        scheduled += claimed
    relay = runtime.relay_due(queue=queue, limit=limit)
    purged_requests = purge_request_fingerprints(
        identity_store, now=datetime.now(timezone.utc)
    )
    return {
        "reclaimed_outbox": reclaimed_outbox,
        "reaped_jobs": reaped_jobs,
        "scheduled": scheduled,
        "published": relay.published,
        "failed": relay.failed,
        "purged_requests": purged_requests,
    }
