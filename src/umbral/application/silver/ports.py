"""Application ports for Silver normalization; infrastructure supplies adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from umbral.application.ingestion.contracts import ImportRun, RawListingSnapshot
from umbral.application.silver.contracts import (
    CanonicalProperty,
    DedupeLink,
    DedupeLinkState,
    GeoResult,
    ListingChange,
    NormalizedListing,
)


class RawSnapshotReader(Protocol):
    """Reads Bronze snapshots that feed normalization."""

    def list_for_run(self, run_id: UUID) -> tuple[RawListingSnapshot, ...]: ...

    def get(self, snapshot_id: UUID) -> RawListingSnapshot | None: ...


class RunReader(Protocol):
    def get(self, run_id: UUID) -> ImportRun | None: ...


class CanonicalPropertyRepository(Protocol):
    def create(
        self,
        *,
        canonical_property_id: UUID,
        first_seen_at: datetime,
        correlation_id: UUID,
        actor_kind: str,
        actor_id: str | None,
    ) -> CanonicalProperty: ...

    def get(self, canonical_property_id: UUID) -> CanonicalProperty | None: ...


class SilverListingRepository(Protocol):
    def insert(self, listing: NormalizedListing) -> None: ...

    def get(self, listing_id: UUID) -> NormalizedListing | None: ...

    def exists(self, *, snapshot_id: UUID, normalizer_version: str) -> bool: ...

    def list_chain(
        self, source_id: str, external_id: str
    ) -> tuple[NormalizedListing, ...]: ...

    def list_canonical(
        self, canonical_property_id: UUID
    ) -> tuple[NormalizedListing, ...]: ...

    def find_dedupe_candidates(
        self,
        *,
        operation: str,
        neighborhood: str | None,
        source_id: str,
        external_id: str,
    ) -> tuple[NormalizedListing, ...]: ...

    def latest_for_source(
        self, source_id: str, external_id: str
    ) -> NormalizedListing | None: ...


class DedupeLinkRepository(Protocol):
    def insert(self, link: DedupeLink) -> None: ...

    def get(self, link_id: UUID) -> DedupeLink | None: ...

    def find_pair(self, a_id: UUID, b_id: UUID) -> DedupeLink | None: ...

    def list_by_state(self, state: DedupeLinkState) -> tuple[DedupeLink, ...]: ...

    def save(self, link: DedupeLink) -> None: ...


class ChangeRepository(Protocol):
    def insert(self, change: ListingChange) -> None: ...

    def list_for_listing(self, listing_id: UUID) -> tuple[ListingChange, ...]: ...

    def list_for_chain(
        self, source_id: str, external_id: str
    ) -> tuple[ListingChange, ...]: ...


class Geocoder(Protocol):
    """Resolves a location to coordinates within an allowed precision."""

    def geocode(
        self, *, location_text: str, neighborhood: str | None, max_precision: str
    ) -> GeoResult: ...
