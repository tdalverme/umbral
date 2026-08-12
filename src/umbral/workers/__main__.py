"""Small operational CLI for worker and scheduler processes."""

from __future__ import annotations

import argparse
import json
import sys
import time
from threading import Event, Thread
from typing import Any

from umbral.infrastructure.observability.runtime import shutdown_observability
from umbral.infrastructure.runtime.heartbeat import HEARTBEAT_INTERVAL_SECONDS
from umbral.workers.scheduler import DEFAULT_DUE_WORK_LIMIT, scheduler_once
from umbral.workers.worker import build_rq_worker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m umbral.workers")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("worker", help="run the durable job worker")
    subparsers.add_parser("scheduler", help="run the UTC scheduler")
    subparsers.add_parser("scheduler-once", help="run one durable scheduler pass")
    return parser


def main(argv: list[str] | None = None, *, dependencies: Any | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        active_dependencies = dependencies
        if active_dependencies is None:
            from umbral.workers.composition import build_process_dependencies

            active_dependencies = build_process_dependencies()
        if (
            args.command == "scheduler"
            and active_dependencies.settings.environment == "preview"
        ):
            return 2
        if args.command == "worker":
            _heartbeat(active_dependencies, "worker")
            stop = Event()
            heartbeat_thread = _start_worker_heartbeat(active_dependencies, stop)
            try:
                build_rq_worker(active_dependencies.queue).work()
                return 0
            finally:
                stop.set()
                if heartbeat_thread is not None:
                    heartbeat_thread.join(timeout=HEARTBEAT_INTERVAL_SECONDS + 5)
        if args.command == "scheduler-once":
            _heartbeat(active_dependencies, "scheduler")
            summary = scheduler_once(
                active_dependencies.runtime,
                queue=active_dependencies.queue,
                identity_store=active_dependencies.identity_store,
                limit=DEFAULT_DUE_WORK_LIMIT,
                agent_purge=getattr(
                    active_dependencies, "agent_checkpoint_purge", None
                ),
                proposal_expire=getattr(
                    active_dependencies, "proposal_expire", None
                ),
                notifications_plan=getattr(
                    active_dependencies, "notifications_plan", None
                ),
                notifications_digest=getattr(
                    active_dependencies, "notifications_digest", None
                ),
            )
            print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
            return 0
        if args.command == "scheduler":
            while True:
                _heartbeat(active_dependencies, "scheduler")
                scheduler_once(
                    active_dependencies.runtime,
                    queue=active_dependencies.queue,
                    identity_store=active_dependencies.identity_store,
                    limit=DEFAULT_DUE_WORK_LIMIT,
                    agent_purge=getattr(
                        active_dependencies, "agent_checkpoint_purge", None
                    ),
                    proposal_expire=getattr(
                        active_dependencies, "proposal_expire", None
                    ),
                    notifications_plan=getattr(
                        active_dependencies, "notifications_plan", None
                    ),
                    notifications_digest=getattr(
                        active_dependencies, "notifications_digest", None
                    ),
                )
                time.sleep(HEARTBEAT_INTERVAL_SECONDS)
        return 2
    except Exception as exc:  # noqa: BLE001 - reported sanitized below
        print(f"{args.command} failed", file=sys.stderr)
        print(_sanitized_exception(exc), file=sys.stderr)
        return 1
    finally:
        shutdown_observability()


def _sanitized_exception(exc: Exception) -> str:
    """Report the failure kind and message with credentials stripped.

    Connection errors often embed URLs with passwords (SQLAlchemy/psycopg);
    this removes ``scheme://user:pass@host`` before printing.
    """
    import re as _re
    import traceback as _traceback

    message = str(exc)
    redacted = _re.sub(
        r"([a-z][a-z0-9+.-]*://)[^/@\s]+@", r"\1***@", message
    )
    lines = [f"kind={type(exc).__name__} message={redacted}"]
    for frame in _traceback.extract_tb(exc.__traceback__)[-6:]:
        lines.append(f"  at {frame.filename}:{frame.lineno} in {frame.name}")
    return "\n".join(lines)


def _heartbeat(dependencies: Any, surface: str) -> None:
    writer = getattr(dependencies, "heartbeat_writer", None)
    if writer is not None:
        writer.observe(surface, state="ready", checks={"runtime_process": "ready"})


def _start_worker_heartbeat(dependencies: Any, stop: Event) -> Thread | None:
    """Publish the worker surface at a bounded cadence while the worker runs."""

    writer = getattr(dependencies, "heartbeat_writer", None)
    if writer is None:
        return None

    def run() -> None:
        while not stop.is_set():
            try:
                _heartbeat(dependencies, "worker")
            except Exception:
                pass
            stop.wait(HEARTBEAT_INTERVAL_SECONDS)

    thread = Thread(target=run, name="worker-heartbeat", daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    raise SystemExit(main())
