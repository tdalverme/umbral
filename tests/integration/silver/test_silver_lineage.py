"""Bronze-Silver lineage walk on the real backend (US3, UM-H2-018)."""

from __future__ import annotations

from tests.integration.silver.conftest import (
    SilverBackend,
    import_batch,
    normalize_service,
)


def test_every_reference_entity_walks_back_to_snapshot_and_run(
    silver_backend: SilverBackend,
) -> None:
    factory, object_store = silver_backend
    finished = import_batch(
        factory,
        object_store,
        name="reference-batch.json",
        source_id="source-a",
        batch_key="lin-1",
    )
    service = normalize_service(factory)
    summary = service.process(finished.run_id)
    assert summary.listings_inserted == 9

    for external_id in [
        "sil-0001",
        "sil-0002",
        "sil-0003",
        "sil-0004",
        "sil-0005",
        "sil-0006",
        "sil-0007",
        "sil-0008",
        "sil-0009",
    ]:
        listing = service.chain("source-a", external_id)[0]
        info = service.lineage(listing.listing_id)
        assert info.snapshot is not None
        assert info.snapshot.snapshot_id == listing.snapshot_id
        assert info.snapshot.source.source_id == "source-a"
        assert info.run is not None
        assert info.run.run_id == finished.run_id
        assert info.run.source.contract_version == "1"
        assert info.listing.normalizer_version == "silver-schema-v1"


def test_lineage_run_reports_parser_version_surrogate(
    silver_backend: SilverBackend,
) -> None:
    factory, object_store = silver_backend
    finished = import_batch(
        factory,
        object_store,
        name="reference-batch.json",
        source_id="source-a",
        batch_key="lin-2",
    )
    service = normalize_service(factory)
    service.process(finished.run_id)
    listing = service.chain("source-a", "sil-0001")[0]
    info = service.lineage(listing.listing_id)
    assert info.run is not None
    assert info.run.source.contract_version == "1"
