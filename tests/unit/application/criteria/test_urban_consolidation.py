# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Urban signal consolidation into observations (fase 3, US2)."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID, uuid4

from tests.fakes.criteria import FakeUrbanSignalRepository
from tests.support.criteria import CriteriaTestContext

from umbral.application.criteria.contracts import RecomputeScope
from umbral.application.silver.contracts import NormalizedListing


def _context_with_signals(
    listing_id: UUID | None, signals: list[Mapping[str, object]]
) -> tuple[CriteriaTestContext, NormalizedListing]:
    context = CriteriaTestContext(
        urban_context_enabled=True,
        urban_signals=FakeUrbanSignalRepository(),
    )
    context.seed_concepts()
    listing = context.add_listing(
        description_text="depto cerca de cafes",
        geometry=(-34.5833, -58.4245),
        geo_precision="exact",
    )
    assert context.urban_signals is not None
    for signal in signals:
        context.urban_signals.insert(
            {
                "signal_id": signal["signal_id"],
                "listing_id": listing.listing_id,
                "signal_type": "cafe",
                "signal_source": "osm",
                "observed_at": None,
                "geometry": signal["geometry"],
                "algorithm_version": "v1",
                "payload": {},
            }
        )
    return context, listing


def test_urban_consolidation_counts_signals_inside_radius() -> None:
    context, listing = _context_with_signals(
        listing_id=None,
        signals=[
            {
                "signal_id": uuid4(),
                "geometry": "POINT(-58.4245 -34.5833)",  # ~0m
            },
            {
                "signal_id": uuid4(),
                "geometry": "POINT(-58.4260 -34.5833)",  # ~150m
            },
            {
                "signal_id": uuid4(),
                "geometry": "POINT(-58.4500 -34.5833)",  # ~2.3km (fuera)
            },
        ],
    )
    summary = context.service.process_extraction(
        RecomputeScope("concept", "proximidad_cafes"),
        job_execution_id=uuid4(),
    )
    assert summary["published"] == 1
    observation = context.observations.rows[-1]
    assert observation.concept_key == "proximidad_cafes"
    assert observation.source == "urban"
    assert observation.value == 2
    assert observation.score == 1.0
    assert observation.state == "active"
    signals = observation.evidence["signals"]
    assert isinstance(signals, list)
    assert len(signals) == 2
    assert all(signal["algorithm_version"] == "v1" for signal in signals)


def test_urban_consolidation_zero_signals_unknown() -> None:
    context, listing = _context_with_signals(listing_id=None, signals=[])
    context.service.process_extraction(
        RecomputeScope("concept", "proximidad_cafes"),
        job_execution_id=uuid4(),
    )
    observation = context.observations.rows[-1]
    assert observation.source == "urban"
    assert observation.value == 0
    assert observation.score == 0.0
    assert observation.evidence["signals"] == []


def test_urban_consolidation_filters_other_signal_types() -> None:
    context, listing = _context_with_signals(
        listing_id=None,
        signals=[
            {
                "signal_id": uuid4(),
                "geometry": "POINT(-58.4245 -34.5833)",
            }
        ],
    )
    assert context.urban_signals is not None
    context.urban_signals.insert(
        {
            "signal_id": uuid4(),
            "listing_id": listing.listing_id,
            "signal_type": "transport",
            "signal_source": "osm",
            "observed_at": None,
            "geometry": "POINT(-58.4245 -34.5833)",
            "algorithm_version": "v1",
            "payload": {},
        }
    )
    context.service.process_extraction(
        RecomputeScope("concept", "proximidad_cafes"),
        job_execution_id=uuid4(),
    )
    observation = context.observations.rows[-1]
    assert observation.value == 1


def test_urban_consolidation_fails_cleanly_without_urban_repo() -> None:
    context = CriteriaTestContext(urban_context_enabled=False)
    context.seed_concepts()
    context.add_listing(
        description_text="depto",
        geometry=(-34.5833, -58.4245),
        geo_precision="exact",
    )
    context.service.process_extraction(
        RecomputeScope("concept", "proximidad_cafes"),
        job_execution_id=uuid4(),
    )
    observation = context.observations.rows[-1]
    assert observation.state == "failed"
    assert observation.failure_code == "criteria.urban_unavailable"
