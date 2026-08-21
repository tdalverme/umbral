"""NormalizeRunService behaviors on in-memory adapters (US1 core + US3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID

import pytest
from tests.fakes.imports import (
    InMemoryImportRunRepository,
    InMemoryRawSnapshotRepository,
)
from tests.fakes.silver import make_normalize_service
from tests.support.silver import (
    build_run,
    load_records,
    snapshot_from_payload,
    store_succeeded_run,
)

from umbral.application.ingestion.contracts import ImportRun
from umbral.application.silver.contracts import (
    SilverPermanentError,
    SilverTransientError,
)
from umbral.application.silver.dedupe_policy import DedupePolicySpec
from umbral.application.silver.service import NormalizeRunService
from umbral.application.silver.silver_schema import SilverSchemaSpec
from umbral.infrastructure.silver.contract_loader import (
    load_dedupe_policy,
    load_silver_schema,
)

VALID_RECORDS = [
    r
    for r in load_records("reference-batch.json")
    if str(r["external_id"]).startswith("sil-000")
]


def _records() -> list[dict[str, object]]:
    return VALID_RECORDS


def _setup(
    schema: SilverSchemaSpec,
    dedupe: DedupePolicySpec,
    now: datetime | None = None,
) -> tuple[NormalizeRunService, ImportRun]:
    snapshots = InMemoryRawSnapshotRepository()
    runs = InMemoryImportRunRepository()
    run = build_run()
    store_succeeded_run(runs, run)
    for record in _records():
        snapshots.insert(
            snapshot_from_payload(
                record, run_id=run.run_id, source_id="source-a", captured_at=now
            )
        )
    service = make_normalize_service(
        snapshots=snapshots,
        runs=runs,
        schema=schema,
        dedupe=dedupe,
        now=now,
    )
    return service, run


def test_reference_run_normalizes_all_valid_snapshots() -> None:
    service, run = _setup(load_silver_schema(), load_dedupe_policy())
    summary = service.process(run.run_id)
    assert summary.total_snapshots == 9
    assert summary.listings_inserted == 9
    assert summary.skipped == 0
    listings = service.listings.list_chain("source-a", "sil-0001")
    assert len(listings) == 1
    assert listings[0].normalizer_version == "silver-schema-v2"
    assert listings[0].geo_precision == "exact"


def test_reprocess_is_idempotent() -> None:
    service, run = _setup(load_silver_schema(), load_dedupe_policy())
    service.process(run.run_id)
    summary = service.process(run.run_id)
    assert summary.listings_inserted == 0
    assert summary.skipped == 9


def test_normalize_service_propagates_new_listing_attributes() -> None:
    schema = load_silver_schema()
    dedupe = load_dedupe_policy()
    snapshots = InMemoryRawSnapshotRepository()
    runs = InMemoryImportRunRepository()
    run = build_run()
    store_succeeded_run(runs, run)
    snapshots.insert(
        snapshot_from_payload(
            {
                "external_id": "attributes-1",
                "operation": "rental",
                "property_type": "apartment",
                "price": 1000,
                "currency": "USD",
                "address_text": "Avenida del Libertador 100",
                "title": "Departamento",
                "surface_covered_m2": 72,
                "bathrooms": 1,
                "toilettes": 1,
                "parking_spaces": 1,
                "age_years": 3,
                "disposition": "Frente",
                "orientation": "SE",
                "media_urls": ["https://img.example.com/one.jpg"],
            },
            run_id=run.run_id,
            contract_version="2",
        )
    )
    service = make_normalize_service(
        snapshots=snapshots, runs=runs, schema=schema, dedupe=dedupe
    )

    service.process(run.run_id)
    listing = service.listings.list_chain("source-a", "attributes-1")[0]

    assert listing.title_text == "Departamento"
    assert listing.surface_covered_m2 == 72.0
    assert listing.bathrooms == 1.0
    assert listing.toilettes == 1.0
    assert listing.parking_spaces == 1.0
    assert listing.age_years == 3.0
    assert listing.disposition == "Frente"
    assert listing.orientation == "SE"
    assert listing.media_urls == ("https://img.example.com/one.jpg",)


def test_chain_versions_share_canonical_and_emit_changes() -> None:
    schema = load_silver_schema()
    dedupe = load_dedupe_policy()
    snapshots = InMemoryRawSnapshotRepository()
    runs = InMemoryImportRunRepository()
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    run = build_run()
    store_succeeded_run(runs, run)

    v1 = dict(_records()[0])
    v2 = dict(_records()[0])
    v2["price"] = 900000
    snapshots.insert(
        snapshot_from_payload(
            v1, run_id=run.run_id, source_id="source-a", captured_at=now
        )
    )
    snapshots.insert(
        snapshot_from_payload(
            v2,
            run_id=run.run_id,
            source_id="source-a",
            captured_at=now + timedelta(hours=1),
        )
    )
    service = make_normalize_service(
        snapshots=snapshots, runs=runs, schema=schema, dedupe=dedupe, now=now
    )
    summary = service.process(run.run_id)
    assert summary.listings_inserted == 2
    assert summary.changes_emitted == 2  # price_value + total_cost
    chain = service.listings.list_chain("source-a", "sil-0001")
    assert len(chain) == 2
    assert chain[0].canonical_property_id == chain[1].canonical_property_id
    changes = service.changes_for_chain("source-a", "sil-0001")
    by_field = {change.field: change for change in changes}
    assert by_field["price_value"].change_type == "price"
    assert by_field["price_value"].before == 850000.0
    assert by_field["price_value"].after == 900000.0
    assert by_field["total_cost"].origin["normalizer_version"] == "silver-schema-v2"


def test_run_must_be_succeeded() -> None:
    service, run = _setup(load_silver_schema(), load_dedupe_policy())
    stored = service.runs.get(run.run_id)
    assert stored is not None
    stored.state = "failed"
    cast(InMemoryImportRunRepository, service.runs).save(stored)

    with pytest.raises(SilverPermanentError):
        service.process(run.run_id)


def test_missing_run_is_transient() -> None:
    service, _ = _setup(load_silver_schema(), load_dedupe_policy())

    with pytest.raises(SilverTransientError):
        service.process(UUID(int=999))
