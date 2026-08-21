"""Reprocess idempotency and normalizer-version isolation (US3, SC-008)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.integration.silver.conftest import (
    SilverBackend,
    import_batch,
    normalize_service,
)

from umbral.application.silver.silver_schema import (
    SilverSchemaSpec,
    parse_silver_schema,
)

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "contracts" / "silver" / "v2" / "silver-schema.json"


def _beta_schema() -> SilverSchemaSpec:
    published = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    published["normalizer_version"] = "silver-schema-v2.beta"
    return parse_silver_schema(published)


def test_reprocessing_same_run_creates_nothing_new(
    silver_backend: SilverBackend,
) -> None:
    factory, object_store = silver_backend
    service = normalize_service(factory)
    finished = import_batch(
        factory,
        object_store,
        name="reference-batch.json",
        source_id="source-a",
        batch_key="rp-1",
    )
    first = service.process(finished.run_id)
    assert first.listings_inserted == 9

    replay = service.process(finished.run_id)
    assert replay.listings_inserted == 0
    assert replay.skipped == 9
    assert replay.changes_emitted == 0
    assert len(service.chain("source-a", "sil-0001")) == 1


def test_new_normalizer_version_preserves_previous_rows(
    silver_backend: SilverBackend,
) -> None:
    factory, object_store = silver_backend
    service = normalize_service(factory)
    finished = import_batch(
        factory,
        object_store,
        name="reference-batch.json",
        source_id="source-a",
        batch_key="rp-2",
    )
    service.process(finished.run_id)

    beta = normalize_service(factory, schema=_beta_schema())
    summary = beta.process(finished.run_id)
    assert summary.listings_inserted == 9
    assert summary.skipped == 0

    chain = beta.chain("source-a", "sil-0001")
    assert len(chain) == 2
    versions = {listing.normalizer_version for listing in chain}
    assert versions == {"silver-schema-v2", "silver-schema-v2.beta"}
    assert chain[0].price_value == chain[1].price_value
