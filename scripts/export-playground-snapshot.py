"""Export a read-only PostGIS slice for the local playground."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from uuid import UUID

from umbral.infrastructure.db.session import SessionProvider
from umbral.infrastructure.playground.exporter import export_playground_snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".data/playground/real-snapshot.json"),
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--radius-m", type=int, default=5000)
    parser.add_argument("--listing-id", action="append", default=[])
    parser.add_argument("--urban-snapshot-id", type=UUID)
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL es requerido para exportar el snapshot")

    provider = SessionProvider(database_url)
    try:
        summary = export_playground_snapshot(
            provider.session_factory,
            args.output,
            listing_ids=tuple(UUID(value) for value in args.listing_id),
            limit=args.limit,
            radius_m=args.radius_m,
            urban_snapshot_id=args.urban_snapshot_id,
        )
    finally:
        provider.close()

    print(
        f"Snapshot exportado: {summary.output_path} "
        f"({summary.listing_count} listings, {summary.feature_count} features)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
