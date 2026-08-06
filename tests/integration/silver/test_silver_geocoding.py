"""Geocoding integration: precision never improves beyond input granularity."""

from __future__ import annotations

from tests.integration.silver.conftest import (
    SilverBackend,
    import_batch,
    normalize_service,
)

from umbral.infrastructure.geocoding.fake import FakeGeocoder


def test_geocoding_upgrades_only_allowed_granularity(
    silver_backend: SilverBackend,
) -> None:
    factory, object_store = silver_backend
    service = normalize_service(factory, geocoder=FakeGeocoder())
    finished = import_batch(
        factory,
        object_store,
        name="reference-batch.json",
        source_id="source-a",
        batch_key="geo-1",
    )
    service.process(finished.run_id)

    # Neighborhood-only -> coordinates with precision "neighborhood" from the
    # registered source.
    neighborhood_only = service.chain("source-a", "sil-0004")[0]
    assert neighborhood_only.geo_precision == "neighborhood"
    assert neighborhood_only.geometry is not None
    assert neighborhood_only.geo_source == "fake.geocoder"

    # Address only, no neighborhood -> the fake has no answer, stays unknown,
    # no invention.
    unknown = service.chain("source-a", "sil-0005")[0]
    assert unknown.geo_precision == "unknown"
    assert unknown.geometry is None
    assert unknown.geo_source is None

    # Source coordinates -> exact, never touched.
    exact = service.chain("source-a", "sil-0001")[0]
    assert exact.geo_precision == "exact"
    assert exact.geo_source is None
