"""Small operational CLI for worker and scheduler processes."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m umbral.workers")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("worker", help="run the durable job worker")
    subparsers.add_parser("scheduler", help="run the UTC scheduler")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Process composition is supplied by the deployment adapter. Keeping the
    # parser side-effect free makes `--help` and smoke checks safe.
    if args.command in {"worker", "scheduler"}:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
