"""In-memory Silver adapters and composition helper for application tests."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from umbral.application.silver.contracts import (
    CanonicalProperty,
    DedupeLink,
    DedupeLinkState,
    GeoResult,
    ListingChange,
    NormalizedListing,
)
from umbral.application.silver.dedupe_policy import DedupePolicySpec
from umbral.application.silver.ports import Geocoder, RawSnapshotReader, RunReader
from umbral.application.silver.service import NormalizeRunService
from umbral.application.silver.silver_schema import SilverSchemaSpec


class InMemoryCanonicalPropertyRepository:
    def __init__(self) -> None:
        self.properties: dict[UUID, CanonicalProperty] = {}

    def create(
        self,
        *,
        canonical_property_id: UUID,
        first_seen_at: datetime,
        correlation_id: UUID,
        actor_kind: str,
        actor_id: str | None,
    ) -> CanonicalProperty:
        del correlation_id, actor_kind, actor_id
        prop = CanonicalProperty(
            canonical_property_id=canonical_property_id,
            state="active",
            first_seen_at=first_seen_at,
            latest_listing_id=None,
        )
        self.properties[canonical_property_id] = prop
        return prop

    def get(self, canonical_property_id: UUID) -> CanonicalProperty | None:
        return self.properties.get(canonical_property_id)


class InMemorySilverListingRepository:
    def __init__(self) -> None:
        self.listings: dict[UUID, NormalizedListing] = {}
        self.snapshot_keys: set[tuple[UUID, str]] = set()

    def insert(self, listing: NormalizedListing) -> None:
        key = (listing.snapshot_id, listing.normalizer_version)
        if key in self.snapshot_keys:
            return
        self.listings[listing.listing_id] = listing
        self.snapshot_keys.add(key)

    def get(self, listing_id: UUID) -> NormalizedListing | None:
        return self.listings.get(listing_id)

    def exists(self, *, snapshot_id: UUID, normalizer_version: str) -> bool:
        return (snapshot_id, normalizer_version) in self.snapshot_keys

    def list_chain(
        self, source_id: str, external_id: str
    ) -> tuple[NormalizedListing, ...]:
        return tuple(
            sorted(
                (
                    listing
                    for listing in self.listings.values()
                    if listing.source.source_id == source_id
                    and listing.external_id == external_id
                ),
                key=lambda listing: listing.last_observed_at,
            )
        )

    def list_canonical(
        self, canonical_property_id: UUID
    ) -> tuple[NormalizedListing, ...]:
        return tuple(
            listing
            for listing in self.listings.values()
            if listing.canonical_property_id == canonical_property_id
        )

    def find_dedupe_candidates(
        self,
        *,
        operation: str,
        neighborhood: str | None,
        source_id: str,
        external_id: str,
    ) -> tuple[NormalizedListing, ...]:
        if neighborhood is None:
            return ()
        key = neighborhood.casefold()
        return tuple(
            listing
            for listing in self.listings.values()
            if listing.operation == operation
            and listing.neighborhood is not None
            and listing.neighborhood.casefold() == key
            and (
                listing.source.source_id != source_id
                or listing.external_id != external_id
            )
        )

    def latest_for_source(
        self, source_id: str, external_id: str
    ) -> NormalizedListing | None:
        chain = self.list_chain(source_id, external_id)
        return chain[-1] if chain else None


class InMemoryDedupeLinkRepository:
    def __init__(self) -> None:
        self.links: dict[UUID, DedupeLink] = {}
        self.pairs: dict[tuple[UUID, UUID], UUID] = {}

    def insert(self, link: DedupeLink) -> None:
        self.links[link.link_id] = link
        self.pairs[(link.listing_a_id, link.listing_b_id)] = link.link_id

    def get(self, link_id: UUID) -> DedupeLink | None:
        return self.links.get(link_id)

    def find_pair(self, a_id: UUID, b_id: UUID) -> DedupeLink | None:
        link_id = self.pairs.get((a_id, b_id))
        return self.links.get(link_id) if link_id is not None else None

    def list_by_state(self, state: DedupeLinkState) -> tuple[DedupeLink, ...]:
        return tuple(link for link in self.links.values() if link.state == state)

    def save(self, link: DedupeLink) -> None:
        existing = self.links.get(link.link_id)
        if existing is None:
            raise KeyError(link.link_id)
        if existing.version != link.version:
            raise ValueError("dedupe link version conflict")
        link.version += 1
        self.links[link.link_id] = link


class InMemoryChangeRepository:
    def __init__(self, listings: InMemorySilverListingRepository | None = None) -> None:
        self.changes: dict[UUID, ListingChange] = {}
        self.listings = listings

    def bind_listings(self, listings: InMemorySilverListingRepository) -> None:
        self.listings = listings

    def insert(self, change: ListingChange) -> None:
        self.changes[change.change_id] = change

    def list_for_listing(self, listing_id: UUID) -> tuple[ListingChange, ...]:
        return tuple(
            change
            for change in self.changes.values()
            if change.listing_id == listing_id
        )

    def list_for_chain(
        self, source_id: str, external_id: str
    ) -> tuple[ListingChange, ...]:
        listing_ids = set()
        if self.listings is not None:
            listing_ids = {
                listing.listing_id
                for listing in self.listings.list_chain(source_id, external_id)
            }
        return tuple(
            change
            for change in self.changes.values()
            if change.listing_id in listing_ids
        )


class FakeGeocoder:
    def __init__(self, points: dict[str, tuple[float, float]] | None = None) -> None:
        self.points = dict(points or {})
        self.source = "fake.geocoder"

    def geocode(
        self, *, location_text: str, neighborhood: str | None, max_precision: str
    ) -> GeoResult:
        del location_text
        key = (neighborhood or "").casefold()
        point = self.points.get(key)
        if point is None:
            return GeoResult(geometry=None, precision="unknown", source=None)
        return GeoResult(
            geometry=point,
            precision="neighborhood" if max_precision == "neighborhood" else "block",
            source=self.source,
        )


def make_normalize_service(
    *,
    listings: InMemorySilverListingRepository | None = None,
    canonicals: InMemoryCanonicalPropertyRepository | None = None,
    links: InMemoryDedupeLinkRepository | None = None,
    changes: InMemoryChangeRepository | None = None,
    snapshots: RawSnapshotReader | None = None,
    runs: RunReader | None = None,
    schema: SilverSchemaSpec,
    dedupe: DedupePolicySpec,
    geocoder: Geocoder | None = None,
    now: datetime | None = None,
) -> NormalizeRunService:
    from tests.fakes.imports import (
        InMemoryImportRunRepository,
        InMemoryRawSnapshotRepository,
    )

    listing_repo = listings or InMemorySilverListingRepository()
    change_repo = changes or InMemoryChangeRepository()
    change_repo.bind_listings(listing_repo)
    service = NormalizeRunService(
        listings=listing_repo,
        canonicals=canonicals or InMemoryCanonicalPropertyRepository(),
        links=links or InMemoryDedupeLinkRepository(),
        changes=change_repo,
        snapshots=snapshots or InMemoryRawSnapshotRepository(),
        runs=runs or InMemoryImportRunRepository(),
        schema=schema,
        dedupe=dedupe,
        geocoder=geocoder,
        clock=lambda: now or datetime.now(timezone.utc),
    )
    return service
