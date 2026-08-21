"""Operator CLI for the criteria concept registry.

Usage (same environment pattern as the other ops CLIs; run with the target
environment's DATABASE_URL set):
    python -m umbral.ops.criteria seed

``seed`` registers every concept of the published seed into the ``concepts``
registry idempotently: a first run reports how many concepts were inserted and
a re-run reports zero. The preference/urban pipelines depend on these rows
(``criterion_bindings.concept_key`` and the chat binding validation reference
them), so run this once after deploying a seed that introduces new concepts.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence
from uuid import uuid4

from umbral.infrastructure.criteria.composition import build_criteria_service
from umbral.workers.composition import build_process_dependencies


def command_seed(_args: argparse.Namespace) -> int:
    deps = build_process_dependencies()
    service = build_criteria_service(
        session_factory=deps.session_provider.session_factory,
        job_runtime=None,  # registry seeding never enqueues jobs
    )
    registered = service.seed_registry(correlation_id=uuid4())
    print(f"registered={registered}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m umbral.ops.criteria",
        description="Operator CLI for the criteria concept registry.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "seed",
        help=(
            "register the published concepts into the registry "
            "(idempotent: re-runs report zero)"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "seed":
        return command_seed(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
