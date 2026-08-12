"""Operator CLI for Bronze import batches (bypasses the session-cookie API).

Usage (same environment pattern as umbral.ops.identity preload):
    python -m umbral.ops.imports submit-batch --file .data/zonaprop-import.json \
        --source-id zonaprop --source-version manual-v1
    python -m umbral.ops.imports get-run --run-id <uuid>

The environment (DATABASE_URL, REDIS_URL, OBJECT_STORE_*) must be the
target environment's; the worker side processes the queued import job.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from typing import Sequence
from uuid import UUID, uuid4

from umbral.application.ingestion.contracts import (
    ImportBatchRequest,
    SourceIdentity,
)
from umbral.domain.audit import AuditActor
from umbral.workers.composition import build_process_dependencies


def _load_json(file_path: Path) -> bytes:
    if not file_path.is_file():
        raise SystemExit(f"batch file not found: {file_path}")
    return file_path.read_bytes()


def command_submit(args: argparse.Namespace) -> int:
    raw = _load_json(Path(args.file))
    if len(raw) > 10 * 1024 * 1024:
        raise SystemExit("batch file exceeds the 10 MiB contract limit")
    deps = build_process_dependencies()
    deps.ingestion.job_runtime = deps.runtime
    request = ImportBatchRequest(
        source=SourceIdentity(
            args.source_id,
            args.source_version,
            args.contract_version,
        ),
        batch_key=args.batch_key or hashlib.sha256(raw).hexdigest(),
        file_format="json",
        file_name=Path(args.file).name,
        raw=raw,
        actor=AuditActor(kind="operator", id="ops-cli"),
        correlation_id=uuid4(),
    )
    snapshot = deps.ingestion.submit(request)
    print(json.dumps(dataclasses.asdict(snapshot), indent=2, default=str))
    return 0


def command_get_run(args: argparse.Namespace) -> int:
    deps = build_process_dependencies()
    snapshot = deps.ingestion.get(UUID(args.run_id))
    print(json.dumps(dataclasses.asdict(snapshot), indent=2, default=str))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m umbral.ops.imports",
        description="Operator CLI for Bronze import batches.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    submit = sub.add_parser("submit-batch", help="submit a JSON import batch")
    submit.add_argument("--file", required=True, help="path to the batch JSON")
    submit.add_argument("--source-id", default="zonaprop")
    submit.add_argument("--source-version", default="manual-v1")
    submit.add_argument("--contract-version", default="1")
    submit.add_argument("--batch-key", default=None, help="opaque idempotency key")
    run_parser = sub.add_parser("get-run", help="print an import run snapshot")
    run_parser.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "submit-batch":
        return command_submit(args)
    return command_get_run(args)


if __name__ == "__main__":
    sys.exit(main())
