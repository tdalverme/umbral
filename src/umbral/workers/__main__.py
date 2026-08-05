"""Small operational CLI for worker and scheduler processes."""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from umbral.infrastructure.observability.runtime import shutdown_observability
from umbral.workers.scheduler import (
    DEFAULT_DUE_WORK_LIMIT,
    HEARTBEAT_INTERVAL_SECONDS,
    scheduler_once,
)
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
            build_rq_worker(active_dependencies.queue).work()
            return 0
        if args.command == "scheduler-once":
            _heartbeat(active_dependencies, "scheduler")
            summary = scheduler_once(
                active_dependencies.runtime,
                queue=active_dependencies.queue,
                identity_store=active_dependencies.identity_store,
                limit=DEFAULT_DUE_WORK_LIMIT,
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
                )
                time.sleep(HEARTBEAT_INTERVAL_SECONDS)
        return 2
    except Exception:
        print(f"{args.command} failed", file=sys.stderr)
        return 1
    finally:
        shutdown_observability()


def _heartbeat(dependencies: Any, surface: str) -> None:
    writer = getattr(dependencies, "heartbeat_writer", None)
    if writer is not None:
        writer.observe(surface, state="ready", checks={"runtime_process": "ready"})


if __name__ == "__main__":
    raise SystemExit(main())
