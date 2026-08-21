"""Pure, transport-independent values and errors for Silver normalization."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from umbral.application.ingestion.contracts import (
    ImportRun,
    RawListingSnapshot,
    SourceIdentity,
)

OperationType = Literal["rental"]
PropertyType = Literal["apartment", "house", "room", "studio", "commercial", "other"]
CurrencyType = Literal["ARS", "USD"]
GeoPrecision = Literal["exact", "block", "neighborhood", "approximate", "unknown"]
CanonicalState = Literal["active"]
DedupeMethod = Literal["deterministic", "proposal"]
DedupeLinkState = Literal["pending", "confirmed", "rejected"]
ChangeType = Literal["price", "text", "attribute", "status"]

ACTIVE_NORMALIZER_VERSION = "silver-schema-v2"


@dataclass(frozen=True, slots=True)
class NormalizedFields:
    """Pure normalization result of one snapshot, before identity assignment."""

    operation: OperationType
    property_type: PropertyType
    price_value: float
    price_currency: CurrencyType
    expenses_value: float | None
    expenses_currency: CurrencyType | None
    total_cost: float
    price_assumptions: Mapping[str, object]
    surface_m2: float | None
    rooms: int | None
    bedrooms: int | None
    floor: int | None
    amenities: tuple[str, ...]
    description_text: str | None
    location_text: str
    neighborhood: str | None
    geo_precision: GeoPrecision
    geometry: tuple[float, float] | None
    geo_source: str | None
    url: str | None
    normalization_errors: tuple[str, ...]
    title_text: str | None = None
    surface_covered_m2: float | None = None
    bathrooms: float | None = None
    toilettes: float | None = None
    parking_spaces: float | None = None
    age_years: float | None = None
    disposition: str | None = None
    orientation: str | None = None
    media_urls: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NormalizedListing:
    listing_id: UUID
    canonical_property_id: UUID
    run_id: UUID
    snapshot_id: UUID
    source: SourceIdentity
    external_id: str
    url: str | None
    published_at: datetime | None
    last_observed_at: datetime
    normalizer_version: str
    operation: OperationType
    property_type: PropertyType
    price_value: float
    price_currency: CurrencyType
    expenses_value: float | None
    expenses_currency: CurrencyType | None
    total_cost: float
    price_assumptions: Mapping[str, object]
    surface_m2: float | None
    rooms: int | None
    bedrooms: int | None
    floor: int | None
    amenities: tuple[str, ...]
    description_text: str | None
    location_text: str
    neighborhood: str | None
    geo_precision: GeoPrecision
    geometry: tuple[float, float] | None
    geo_source: str | None
    normalization_errors: tuple[str, ...]
    price_changes: tuple[Mapping[str, object], ...] = ()
    title_text: str | None = None
    surface_covered_m2: float | None = None
    bathrooms: float | None = None
    toilettes: float | None = None
    parking_spaces: float | None = None
    age_years: float | None = None
    disposition: str | None = None
    orientation: str | None = None
    media_urls: tuple[str, ...] = ()


@dataclass(slots=True)
class CanonicalProperty:
    canonical_property_id: UUID
    state: CanonicalState
    first_seen_at: datetime
    latest_listing_id: UUID | None
    version: int = 1


@dataclass(slots=True)
class DedupeLink:
    link_id: UUID
    listing_a_id: UUID
    listing_b_id: UUID
    method: DedupeMethod
    state: DedupeLinkState
    fingerprint: str | None
    score: float | None
    evidence: Mapping[str, object]
    created_at: datetime
    version: int = 1
    decided_by: str | None = None
    decided_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ListingChange:
    change_id: UUID
    listing_id: UUID
    previous_listing_id: UUID | None
    change_type: ChangeType
    field: str
    before: object
    after: object
    origin: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class GeoResult:
    geometry: tuple[float, float] | None
    precision: GeoPrecision
    source: str | None


@dataclass(frozen=True, slots=True)
class NormalizeSummary:
    run_id: UUID
    total_snapshots: int
    listings_inserted: int
    skipped: int
    changes_emitted: int
    links_created: int
    proposals_created: int


@dataclass(frozen=True, slots=True)
class LineageInfo:
    listing: NormalizedListing
    snapshot: RawListingSnapshot | None
    run: ImportRun | None


class SilverError(Exception):
    """Base class for sanitized Silver normalization failures."""

    code = "silver.error"


class SilverPermanentError(SilverError):
    """A terminal processing failure with an actionable code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


class SilverTransientError(SilverError):
    """A bounded, retryable failure explicitly declared by the worker."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


class ListingNotFound(SilverError):
    code = "silver.listing_not_found"

    def __init__(self, listing_id: UUID) -> None:
        self.listing_id = listing_id
        super().__init__(f"silver listing not found: {listing_id}")


class DedupeLinkNotFound(SilverError):
    code = "silver.dedupe_link_not_found"

    def __init__(self, link_id: UUID) -> None:
        self.link_id = link_id
        super().__init__(f"dedupe link not found: {link_id}")


class DedupeLinkStateError(SilverError):
    code = "silver.dedupe_link_state"

    def __init__(self, link_id: UUID, detail: str) -> None:
        self.link_id = link_id
        self.detail = detail
        super().__init__(detail)
