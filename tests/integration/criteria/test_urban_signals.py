"""Integration (P1): urban context signals with traceability over real Postgres."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from tests.integration.criteria.conftest import (
    build_criteria_service,
    seed_silver_listings,
)

from umbral.infrastructure.db.models.criteria import UrbanSignal as UrbanSignalModel


class _UrbanSource:
    def fetch(self, listing: Any, signal_type: str) -> tuple[dict[str, object], ...]:
        return (
            {
                "source": "fixture",
                "algorithm_version": "v1",
                "geometry": (-58.4, -34.6),
                "payload": {"name": "cafe-1"},
            },
        )


def test_urban_signals_are_traceable_and_respect_precision(
    criteria_backend: Any,
) -> None:
    factory = criteria_backend
    listing_ids = seed_silver_listings(factory, count=1)
    service = build_criteria_service(
        factory,
        urban_context_enabled=True,
        urban_source=_UrbanSource(),
    )
    count = service.ingest_urban_signals(
        listing_id=listing_ids[0],
        signal_type="cafe",
        correlation_id=uuid4(),
    )
    assert count == 1
    with factory() as session:
        rows = list(session.execute(select(UrbanSignalModel)).scalars())
    assert len(rows) == 1
    signal = rows[0]
    assert signal.signal_source == "fixture"
    assert signal.algorithm_version == "v1"
    # listings are seeded with neighborhood precision -> geometry must be null
    assert signal.geometry is None


def test_urban_signals_disabled_have_no_effect(criteria_backend: Any) -> None:
    factory = criteria_backend
    listing_ids = seed_silver_listings(factory, count=1)
    service = build_criteria_service(factory, urban_context_enabled=False)
    count = service.ingest_urban_signals(
        listing_id=listing_ids[0],
        signal_type="cafe",
        correlation_id=uuid4(),
    )
    assert count == 0
