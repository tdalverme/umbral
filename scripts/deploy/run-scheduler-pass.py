"""Run one scheduler pass inside a deployed Railway service environment.

Used by the promote pipeline so the scheduler surface heartbeat and any
pending outbox relay are fresh for the smoke regardless of the cron
cadence or reused deployments. Composes directly so a broken scheduler
environment surfaces a full traceback instead of a swallowed failure.
"""

from umbral.workers.composition import build_process_dependencies
from umbral.workers.scheduler import DEFAULT_DUE_WORK_LIMIT, scheduler_once

deps = build_process_dependencies()
writer = getattr(deps, "heartbeat_writer", None)
if writer is not None:
    writer.observe("scheduler", state="ready", checks={"runtime_process": "ready"})
summary = scheduler_once(
    deps.runtime,
    queue=deps.queue,
    identity_store=deps.identity_store,
    limit=DEFAULT_DUE_WORK_LIMIT,
)
print("scheduler-once summary:", summary)
