"""Change detection between chain versions on the real backend (US3)."""

from __future__ import annotations

from tests.integration.silver.conftest import (
    SilverBackend,
    import_batch,
    normalize_service,
)


def test_price_and_text_changes_are_recorded_with_before_after_origin(
    silver_backend: SilverBackend,
) -> None:
    factory, object_store = silver_backend
    service = normalize_service(factory)

    v1 = import_batch(
        factory,
        object_store,
        name="changes-v1.json",
        source_id="source-a",
        batch_key="v1",
    )
    service.process(v1.run_id)

    v2 = import_batch(
        factory,
        object_store,
        name="changes-v2.json",
        source_id="source-a",
        batch_key="v2",
    )
    summary = service.process(v2.run_id)
    assert summary.listings_inserted == 1
    assert summary.changes_emitted == 3  # price_value + total_cost + description_text

    chain = service.chain("source-a", "chg-0001")
    assert len(chain) == 2
    assert chain[0].canonical_property_id == chain[1].canonical_property_id

    changes = service.changes_for_chain("source-a", "chg-0001")
    by_field = {change.field: change for change in changes}
    assert by_field["price_value"].change_type == "price"
    assert by_field["price_value"].before == 850000.0
    assert by_field["price_value"].after == 900000.0
    assert by_field["description_text"].change_type == "text"
    assert by_field["price_value"].origin["normalizer_version"] == "silver-schema-v2"
    assert by_field["price_value"].previous_listing_id == chain[0].listing_id


def test_identical_normalized_republish_emits_zero_changes(
    silver_backend: SilverBackend,
) -> None:
    factory, object_store = silver_backend
    service = normalize_service(factory)

    v1 = import_batch(
        factory,
        object_store,
        name="changes-v1.json",
        source_id="source-a",
        batch_key="r1",
    )
    service.process(v1.run_id)

    # Only media_urls differs (not a normalized change field).
    v2 = import_batch(
        factory,
        object_store,
        name="changes-v2-identical.json",
        source_id="source-a",
        batch_key="r2",
    )
    summary = service.process(v2.run_id)
    assert summary.listings_inserted == 1
    assert summary.changes_emitted == 0
    assert len(service.chain("source-a", "chg-0001")) == 2
