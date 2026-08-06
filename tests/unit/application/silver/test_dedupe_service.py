"""Dedupe link creation, transitions and canonical resolution (US2)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID

import pytest
from tests.fakes.imports import (
    InMemoryImportRunRepository,
    InMemoryRawSnapshotRepository,
)
from tests.fakes.silver import make_normalize_service
from tests.support.silver import build_run, snapshot_from_payload, store_succeeded_run

from umbral.application.ingestion.contracts import ImportRun
from umbral.application.silver.contracts import (
    DedupeLinkNotFound,
    DedupeLinkStateError,
)
from umbral.application.silver.service import NormalizeRunService
from umbral.infrastructure.silver.contract_loader import (
    load_dedupe_policy,
    load_silver_schema,
)

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _record(
    external_id: str, *, source_price: float | None = None
) -> dict[str, object]:
    from tests.support.silver import load_records

    record = next(
        r
        for r in load_records("reference-batch.json")
        if r["external_id"] == external_id
    )
    if source_price is not None:
        record = dict(record)
        record["price"] = source_price
    return record


def _service(
    *source_ids: str,
) -> tuple[NormalizeRunService, list[ImportRun]]:
    schema = load_silver_schema()
    dedupe = load_dedupe_policy()
    snapshots = InMemoryRawSnapshotRepository()
    runs = InMemoryImportRunRepository()
    registered: list[ImportRun] = []
    for source_id in source_ids:
        run = build_run(source_id=source_id)
        store_succeeded_run(runs, run)
        registered.append(run)
    service = make_normalize_service(
        snapshots=snapshots, runs=runs, schema=schema, dedupe=dedupe, now=NOW
    )
    return service, registered


def _process_record(
    service: NormalizeRunService,
    run: ImportRun,
    record: dict[str, object],
    *,
    source_id: str,
) -> None:
    cast(InMemoryRawSnapshotRepository, service.snapshots).insert(
        snapshot_from_payload(
            record, run_id=run.run_id, source_id=source_id, captured_at=NOW
        )
    )
    service.process(run.run_id)


def test_exact_cross_source_duplicates_share_one_canonical() -> None:
    service, (run_a, run_b) = _service("source-a", "source-b")
    _process_record(service, run_a, _record("sil-0001"), source_id="source-a")
    _process_record(service, run_b, _record("sil-0001"), source_id="source-b")

    confirmed = service.links_by_state("confirmed")
    assert len(confirmed) == 1
    link = confirmed[0]
    assert link.method == "deterministic"
    assert link.fingerprint is not None
    assert "fields" in link.evidence

    canonical_a = service.listings.get(link.listing_a_id)
    canonical_b = service.listings.get(link.listing_b_id)
    assert canonical_a is not None and canonical_b is not None
    assert canonical_a.canonical_property_id == canonical_b.canonical_property_id
    assert len(service.canonical_listings(canonical_a.canonical_property_id)) == 2


def test_ambiguous_pairs_become_pending_proposals_never_merge() -> None:
    service, (run_a, run_b) = _service("source-a", "source-b")
    _process_record(service, run_a, _record("sil-0001"), source_id="source-a")
    _process_record(
        service, run_b, _record("sil-0001", source_price=880000), source_id="source-b"
    )

    proposals = service.links_by_state("pending")
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.method == "proposal"
    assert proposal.score is not None and proposal.score >= 0.6
    listing_a = service.listings.get(proposal.listing_a_id)
    listing_b = service.listings.get(proposal.listing_b_id)
    assert listing_a is not None and listing_b is not None
    assert listing_a.canonical_property_id != listing_b.canonical_property_id


def test_missing_strong_field_degrades_to_no_link() -> None:
    service, (run_a, run_b) = _service("source-a", "source-b")
    record = _record("sil-0001")
    record["surface_m2"] = None
    _process_record(service, run_a, record, source_id="source-a")
    _process_record(service, run_b, _record("sil-0001"), source_id="source-b")

    assert service.links_by_state("pending") == ()
    assert service.links_by_state("confirmed") == ()


def test_confirm_and_reject_transitions_are_audited() -> None:
    service, (run_a, run_b, run_c) = _service("source-a", "source-b", "source-c")
    _process_record(service, run_a, _record("sil-0001"), source_id="source-a")
    _process_record(
        service, run_b, _record("sil-0001", source_price=880000), source_id="source-b"
    )
    _process_record(
        service, run_c, _record("sil-0001", source_price=900000), source_id="source-c"
    )
    pending = service.links_by_state("pending")
    assert len(pending) == 3

    confirmed = service.confirm_link(pending[0].link_id, actor_id="operator-1")
    assert confirmed.state == "confirmed"
    assert confirmed.decided_by == "operator-1"
    assert confirmed.decided_at is not None

    with pytest.raises(DedupeLinkStateError):
        service.confirm_link(pending[0].link_id, actor_id="operator-1")

    rejected = service.reject_link(pending[1].link_id, actor_id="operator-2")
    assert rejected.state == "rejected"
    assert rejected.decided_by == "operator-2"


def test_deciding_an_unknown_link_raises_not_found() -> None:
    service, _ = _service("source-a")
    with pytest.raises(DedupeLinkNotFound):
        service.confirm_link(UUID(int=777), actor_id="operator-1")
