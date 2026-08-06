"""End-to-end US1: import -> normalize -> reimport idempotency on real backend."""

from __future__ import annotations

from tests.integration.silver.conftest import (
    SilverBackend,
    import_batch,
    normalize_service,
)


def test_reimport_same_identity_does_not_duplicate_silver(
    silver_backend: SilverBackend,
) -> None:
    factory, object_store = silver_backend
    service = normalize_service(factory)

    first = import_batch(
        factory,
        object_store,
        name="reference-batch.json",
        source_id="source-a",
        batch_key="same-key",
    )
    service.process(first.run_id)

    # Bronze identity idempotency returns the same run; Silver replay is a no-op.
    second = import_batch(
        factory,
        object_store,
        name="reference-batch.json",
        source_id="source-a",
        batch_key="same-key",
    )
    assert second.run_id == first.run_id
    summary = service.process(second.run_id)
    assert summary.total_snapshots == 9
    assert summary.listings_inserted == 0
    assert summary.skipped == 9

    assert len(service.chain("source-a", "sil-0001")) == 1
