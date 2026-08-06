"""Full normalization pipeline on real Postgres + object storage (US1)."""

from __future__ import annotations

from tests.integration.silver.conftest import (
    SilverBackend,
    import_batch,
    normalize_service,
)

from umbral.application.silver.contracts import ListingNotFound
from umbral.infrastructure.db.repositories.imports import (
    SqlAlchemyRawSnapshotRepository,
)


def test_reference_batch_normalizes_to_silver_end_to_end(
    silver_backend: SilverBackend,
) -> None:
    factory, object_store = silver_backend
    finished = import_batch(
        factory,
        object_store,
        name="reference-batch.json",
        source_id="source-a",
        batch_key="e2e-1",
    )
    assert finished.accepted == 9

    service = normalize_service(factory)
    summary = service.process(finished.run_id)
    assert summary.total_snapshots == 9
    assert summary.listings_inserted == 9
    assert summary.skipped == 0

    sil_0001 = service.chain("source-a", "sil-0001")
    assert len(sil_0001) == 1
    listing = sil_0001[0]
    assert listing.normalizer_version == "silver-schema-v1"
    assert listing.price_currency == "ARS"
    assert listing.total_cost == 850000.0 + 65000.0
    assert listing.geo_precision == "exact"
    assert listing.source.source_id == "source-a"
    assert listing.external_id == "sil-0001"
    assert listing.url == "https://example.com/listings/sil-0001"

    sil_0004 = service.chain("source-a", "sil-0004")[0]
    assert sil_0004.geo_precision == "neighborhood"
    assert sil_0004.geometry is None

    sil_0005 = service.chain("source-a", "sil-0005")[0]
    assert sil_0005.geo_precision == "unknown"

    assert (
        len(SqlAlchemyRawSnapshotRepository(factory).list_for_run(finished.run_id)) == 9
    )


def test_read_and_lineage_contract(silver_backend: SilverBackend) -> None:
    factory, object_store = silver_backend
    finished = import_batch(
        factory,
        object_store,
        name="reference-batch.json",
        source_id="source-a",
        batch_key="e2e-2",
    )
    service = normalize_service(factory)
    service.process(finished.run_id)
    listing = service.chain("source-a", "sil-0001")[0]

    info = service.lineage(listing.listing_id)
    assert info.snapshot is not None
    assert info.snapshot.snapshot_id == listing.snapshot_id
    assert info.run is not None
    assert info.run.run_id == finished.run_id

    from uuid import uuid4

    try:
        service.get_listing(uuid4())
    except ListingNotFound:
        pass
    else:
        raise AssertionError("expected ListingNotFound")
