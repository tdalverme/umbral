"""In-memory Silver repository guard behaviors (uniqueness, order, locking)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from tests.fakes.silver import (
    InMemoryCanonicalPropertyRepository,
    InMemoryDedupeLinkRepository,
    InMemorySilverListingRepository,
)
from tests.support.silver import listing_from_payload

from umbral.application.silver.contracts import DedupeLink, NormalizedListing

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _listing(
    source_id: str, external_id: str, *, captured_at: datetime
) -> NormalizedListing:
    listing = listing_from_payload(
        {
            "external_id": external_id,
            "operation": "rental",
            "property_type": "apartment",
            "price": 850000,
            "currency": "ARS",
            "expenses": 65000,
            "address_text": "Av. Corrientes 2400, San Nicolas",
            "neighborhood": "San Nicolas",
            "latitude": -34.6037,
            "longitude": -58.401,
            "surface_m2": 55,
            "rooms": 2,
            "bedrooms": 1,
            "floor": 4,
        },
        source_id=source_id,
    )
    import dataclasses

    return dataclasses.replace(listing, last_observed_at=captured_at)


def test_snapshot_version_guard_prevents_duplicates() -> None:
    repo = InMemorySilverListingRepository()
    first = _listing("source-a", "e-1", captured_at=NOW)
    repo.insert(first)
    repo.insert(first)
    assert repo.exists(
        snapshot_id=first.snapshot_id, normalizer_version=first.normalizer_version
    )
    assert len(repo.listings) == 1


def test_chain_is_ordered_by_captured_at() -> None:
    repo = InMemorySilverListingRepository()
    older = _listing("source-a", "e-1", captured_at=NOW)
    newer = _listing("source-a", "e-1", captured_at=NOW + timedelta(hours=1))
    repo.insert(older)
    repo.insert(newer)
    chain = repo.list_chain("source-a", "e-1")
    assert [listing.last_observed_at for listing in chain] == sorted(
        listing.last_observed_at for listing in chain
    )
    assert repo.latest_for_source("source-a", "e-1") == chain[-1]


def test_dedupe_candidates_exclude_same_chain_only() -> None:
    repo = InMemorySilverListingRepository()
    repo.insert(_listing("source-a", "e-1", captured_at=NOW))
    repo.insert(_listing("source-a", "e-2", captured_at=NOW))
    candidates = repo.find_dedupe_candidates(
        operation="rental",
        neighborhood="San Nicolas",
        source_id="source-a",
        external_id="e-1",
    )
    assert [candidate.external_id for candidate in candidates] == ["e-2"]


def test_dedupe_candidates_require_neighborhood() -> None:
    repo = InMemorySilverListingRepository()
    repo.insert(_listing("source-a", "e-1", captured_at=NOW))
    assert (
        repo.find_dedupe_candidates(
            operation="rental",
            neighborhood=None,
            source_id="source-b",
            external_id="e-2",
        )
        == ()
    )


def test_dedupe_link_version_conflict_is_rejected() -> None:
    repo = InMemoryDedupeLinkRepository()
    a = _listing("source-a", "e-1", captured_at=NOW)
    b = _listing("source-b", "e-1", captured_at=NOW)
    if a.listing_id > b.listing_id:
        a, b = b, a
    link = DedupeLink(
        link_id=uuid4(),
        listing_a_id=a.listing_id,
        listing_b_id=b.listing_id,
        method="proposal",
        state="pending",
        fingerprint=None,
        score=0.8,
        evidence={"version": "dedupe-policy-v1", "method": "proposal"},
        created_at=NOW,
    )
    repo.insert(link)
    assert repo.find_pair(a.listing_id, b.listing_id) is not None

    # A stale version read elsewhere must be rejected on save.
    stale = DedupeLink(
        link_id=link.link_id,
        listing_a_id=a.listing_id,
        listing_b_id=b.listing_id,
        method="proposal",
        state="pending",
        fingerprint=None,
        score=0.8,
        evidence={"version": "dedupe-policy-v1", "method": "proposal"},
        created_at=NOW,
        version=999,
    )
    with pytest.raises(ValueError):
        repo.save(stale)

    fresh = repo.get(link.link_id)
    assert fresh is not None
    fresh.state = "confirmed"
    repo.save(fresh)
    reloaded = repo.get(link.link_id)
    assert reloaded is not None and reloaded.state == "confirmed"


def test_canonical_repo_creates_and_reads() -> None:
    repo = InMemoryCanonicalPropertyRepository()
    created = repo.create(
        canonical_property_id=uuid4(),
        first_seen_at=NOW,
        correlation_id=uuid4(),
        actor_kind="system",
        actor_id=None,
    )
    assert repo.get(created.canonical_property_id) is not None
