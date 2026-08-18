"""PostGIS adapter that turns category geometry into per-listing distance buckets."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from umbral.application.urban.contract import UrbanContract

SessionFactory = Callable[[], Session]


class SqlAlchemyDistanceCalculator:
    """Compute distance buckets for one listing from ``urban_categories``.

    Each category yields one list of metre distances (its features within the
    contract radius); every primitive metric of that category maps to the same
    list, matching what ``UrbanSignalCalculator`` consumes.
    """

    def __init__(
        self, session_factory: SessionFactory, contract: UrbanContract
    ) -> None:
        self.session_factory = session_factory
        self.contract = contract

    def for_listing(
        self,
        listing_id: UUID,
        snapshot_id: UUID,
        *,
        radius_m: int,
    ) -> Mapping[str, Mapping[str, list[float]]]:
        statement = text(
            """
            SELECT uc.category, ST_Distance(
                sl.geometry::geography, uc.geometry::geography
            ) AS distance_m
            FROM silver_listings sl
            JOIN urban_categories uc ON uc.snapshot_id = :snapshot
            WHERE sl.id = :listing
              AND sl.geometry IS NOT NULL
              AND uc.geometry IS NOT NULL
              AND ST_DWithin(
                  sl.geometry::geography, uc.geometry::geography, :radius
              )
            ORDER BY uc.category, distance_m
            """
        )
        by_category: dict[str, list[float]] = {}
        with self.session_factory() as session:
            for row in session.execute(
                statement,
                {
                    "snapshot": snapshot_id,
                    "listing": listing_id,
                    "radius": radius_m,
                },
            ):
                category = str(row.category)
                by_category.setdefault(category, []).append(float(row.distance_m))
        result: dict[str, Mapping[str, list[float]]] = {}
        for category, distances in by_category.items():
            metrics = self._metrics_for(category)
            if not metrics:
                continue
            result[category] = {metric: list(distances) for metric in metrics}
        return result

    def _metrics_for(self, category: str) -> tuple[str, ...]:
        spec = self.contract.primitives.get(category)
        if spec is None:
            spec = self.contract.linear_primitives.get(category)
        if spec is None:
            return ()
        return tuple(metric.name for metric in spec)
