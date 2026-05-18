"""Calcula senales urbanas cacheadas para analyzed_listings con coordenadas."""

from __future__ import annotations

import argparse
import sys

import structlog

from umbral.database import AnalyzedListingRepository, UrbanSignalRepository

logger = structlog.get_logger()


def compute_urban_signals(limit: int = 500) -> dict:
    analyzed_repo = AnalyzedListingRepository()
    urban_repo = UrbanSignalRepository()
    listings = analyzed_repo.get_active_with_coordinates(limit=limit)
    stats = {"processed": 0, "computed": 0, "errors": 0}

    for listing in listings:
        stats["processed"] += 1
        try:
            urban_repo.compute_for_listing(listing)
            stats["computed"] += 1
        except Exception as exc:
            stats["errors"] += 1
            logger.warning(
                "No se pudieron calcular senales urbanas",
                analyzed_listing_id=listing.get("id"),
                error=str(exc),
            )

    logger.info("Backfill de senales urbanas completado", **stats)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Calcula senales urbanas para listings activos")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    stats = compute_urban_signals(limit=args.limit)
    sys.exit(0 if stats["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
