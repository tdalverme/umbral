"""Orchestration for Silver normalization.

The service reads Bronze snapshots of a succeeded import run, normalizes each
against the versioned silver-schema contract, persists immutable Silver rows,
resolves canonical properties (within-source chains plus deterministic
cross-source fingerprint dedupe), emits non-destructive dedupe links and
records field-level changes between consecutive chain versions. Reprocessing is
idempotent through the ``(snapshot_id, normalizer_version)`` guard.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal, cast
from uuid import UUID, uuid4

from umbral.application.ingestion.contracts import SourceIdentity
from umbral.application.silver.contracts import (
    DedupeLink,
    DedupeLinkNotFound,
    DedupeLinkState,
    DedupeLinkStateError,
    GeoPrecision,
    LineageInfo,
    ListingChange,
    ListingNotFound,
    NormalizedFields,
    NormalizedListing,
    NormalizeSummary,
    SilverPermanentError,
    SilverTransientError,
)
from umbral.application.silver.dedupe_policy import (
    DedupePolicySpec,
    evaluate_pair,
)
from umbral.application.silver.ports import (
    CanonicalPropertyRepository,
    ChangeRepository,
    DedupeLinkRepository,
    Geocoder,
    RawSnapshotReader,
    RunReader,
    SilverListingRepository,
)
from umbral.application.silver.silver_schema import (
    SilverSchemaSpec,
    compare_listings,
    normalize_snapshot,
)

ChangeType = Literal["price", "text", "attribute", "status"]

SILVER_NORMALIZE_JOB_TYPE = "ingestion.normalize_batch"

Clock = Callable[[], datetime]

_PRECISION_ORDER: dict[str, int] = {
    "unknown": 0,
    "approximate": 1,
    "neighborhood": 2,
    "block": 3,
    "exact": 4,
}


class NormalizeRunService:
    def __init__(
        self,
        *,
        listings: SilverListingRepository,
        canonicals: CanonicalPropertyRepository,
        links: DedupeLinkRepository,
        changes: ChangeRepository,
        snapshots: RawSnapshotReader,
        runs: RunReader,
        schema: SilverSchemaSpec,
        dedupe: DedupePolicySpec,
        geocoder: Geocoder | None = None,
        clock: Clock | None = None,
    ) -> None:
        self.listings = listings
        self.canonicals = canonicals
        self.links = links
        self.changes = changes
        self.snapshots = snapshots
        self.runs = runs
        self.schema = schema
        self.dedupe = dedupe
        self.geocoder = geocoder
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def normalizer_version(self) -> str:
        return self.schema.normalizer_version

    def process(self, run_id: UUID) -> NormalizeSummary:
        run = self.runs.get(run_id)
        if run is None:
            raise SilverTransientError(
                "silver.run_not_ready", "import run is not yet visible"
            )
        if run.state != "succeeded":
            raise SilverPermanentError(
                "silver.run_not_succeeded",
                f"import run is not succeeded: {run.state}",
            )
        snapshots = self.snapshots.list_for_run(run_id)

        listings_inserted = 0
        skipped = 0
        changes_emitted = 0
        links_created = 0
        proposals_created = 0
        for snapshot in snapshots:
            if self.listings.exists(
                snapshot_id=snapshot.snapshot_id,
                normalizer_version=self.normalizer_version,
            ):
                skipped += 1
                continue

            fields = normalize_snapshot(snapshot, self.schema)
            if self.geocoder is not None:
                fields = self._maybe_geocode(fields)

            existing_chain = self.listings.list_chain(
                snapshot.source.source_id, snapshot.external_id
            )
            previous = existing_chain[-1] if existing_chain else None
            canonical_id = (
                previous.canonical_property_id if previous is not None else None
            )

            candidates = self.listings.find_dedupe_candidates(
                operation=fields.operation,
                neighborhood=fields.neighborhood,
                source_id=snapshot.source.source_id,
                external_id=snapshot.external_id,
            )
            deterministic_match = self._first_deterministic(
                candidates,
                fields,
                source=snapshot.source,
                external_id=snapshot.external_id,
            )
            if canonical_id is None and deterministic_match is not None:
                canonical_id = deterministic_match.canonical_property_id
            if canonical_id is None:
                created = self.canonicals.create(
                    canonical_property_id=uuid4(),
                    first_seen_at=self.clock(),
                    correlation_id=run_id,
                    actor_kind="system",
                    actor_id=None,
                )
                canonical_id = created.canonical_property_id

            listing = _build_listing(
                snapshot_id=snapshot.snapshot_id,
                run_id=run_id,
                canonical_property_id=canonical_id,
                snapshot=snapshot,
                fields=fields,
                normalizer_version=self.normalizer_version,
                listing_id=uuid4(),
            )
            self.listings.insert(listing)
            listings_inserted += 1

            changes_emitted += self._emit_changes(
                listing=listing, previous=previous, snapshot=snapshot, run_id=run_id
            )

            for candidate in candidates:
                pair = _ordered_pair(listing, candidate)
                if (
                    self.links.find_pair(pair[0].listing_id, pair[1].listing_id)
                    is not None
                ):
                    continue
                evaluation = evaluate_pair(pair[0], pair[1], self.dedupe)
                if evaluation.method is None or evaluation.state is None:
                    continue
                link = DedupeLink(
                    link_id=uuid4(),
                    listing_a_id=pair[0].listing_id,
                    listing_b_id=pair[1].listing_id,
                    method=evaluation.method,
                    state=evaluation.state,
                    fingerprint=evaluation.fingerprint,
                    score=evaluation.score,
                    evidence=evaluation.evidence,
                    created_at=self.clock(),
                )
                self.links.insert(link)
                if evaluation.method == "deterministic":
                    links_created += 1
                else:
                    proposals_created += 1

        return NormalizeSummary(
            run_id=run_id,
            total_snapshots=len(snapshots),
            listings_inserted=listings_inserted,
            skipped=skipped,
            changes_emitted=changes_emitted,
            links_created=links_created,
            proposals_created=proposals_created,
        )

    def get_listing(self, listing_id: UUID) -> NormalizedListing:
        listing = self.listings.get(listing_id)
        if listing is None:
            raise ListingNotFound(listing_id)
        return listing

    def chain(self, source_id: str, external_id: str) -> tuple[NormalizedListing, ...]:
        return self.listings.list_chain(source_id, external_id)

    def canonical_listings(
        self, canonical_property_id: UUID
    ) -> tuple[NormalizedListing, ...]:
        return self.listings.list_canonical(canonical_property_id)

    def changes_for_listing(self, listing_id: UUID) -> tuple[ListingChange, ...]:
        return self.changes.list_for_listing(listing_id)

    def changes_for_chain(
        self, source_id: str, external_id: str
    ) -> tuple[ListingChange, ...]:
        return self.changes.list_for_chain(source_id, external_id)

    def links_by_state(self, state: DedupeLinkState) -> tuple[DedupeLink, ...]:
        return self.links.list_by_state(state)

    def lineage(self, listing_id: UUID) -> LineageInfo:
        listing = self.get_listing(listing_id)
        return LineageInfo(
            listing=listing,
            snapshot=self.snapshots.get(listing.snapshot_id),
            run=self.runs.get(listing.run_id),
        )

    def confirm_link(self, link_id: UUID, *, actor_id: str) -> DedupeLink:
        return self._decide_link(link_id, state="confirmed", actor_id=actor_id)

    def reject_link(self, link_id: UUID, *, actor_id: str) -> DedupeLink:
        return self._decide_link(link_id, state="rejected", actor_id=actor_id)

    def _decide_link(
        self, link_id: UUID, *, state: DedupeLinkState, actor_id: str
    ) -> DedupeLink:
        link = self.links.get(link_id)
        if link is None:
            raise DedupeLinkNotFound(link_id)
        if link.method != "proposal":
            raise DedupeLinkStateError(link_id, "only proposal links can be decided")
        if link.state != "pending":
            raise DedupeLinkStateError(link_id, f"link is not pending: {link.state}")
        link.state = state
        link.decided_by = actor_id
        link.decided_at = self.clock()
        self.links.save(link)
        return link

    def _emit_changes(
        self,
        *,
        listing: NormalizedListing,
        previous: NormalizedListing | None,
        snapshot: object,
        run_id: UUID,
    ) -> int:
        if previous is None:
            return 0
        emitted = 0
        diffs = compare_listings(previous, listing, self.schema)
        for field, (change_type, before, after) in diffs.items():
            change = ListingChange(
                change_id=uuid4(),
                listing_id=listing.listing_id,
                previous_listing_id=previous.listing_id,
                change_type=cast(ChangeType, change_type),
                field=field,
                before=_json_safe(before),
                after=_json_safe(after),
                origin={
                    "previous_snapshot_id": str(previous.snapshot_id),
                    "new_snapshot_id": str(listing.snapshot_id),
                    "run_id": str(run_id),
                    "normalizer_version": self.normalizer_version,
                },
            )
            self.changes.insert(change)
            emitted += 1
        return emitted

    def _first_deterministic(
        self,
        candidates: tuple[NormalizedListing, ...],
        fields: NormalizedFields,
        *,
        source: SourceIdentity,
        external_id: str,
    ) -> NormalizedListing | None:
        for candidate in candidates:
            listing = _listing_from_fields(
                fields,
                source=source,
                external_id=external_id,
                canonical_id=candidate.canonical_property_id,
                run_id=candidate.run_id,
                snapshot_id=candidate.snapshot_id,
                normalizer_version=self.normalizer_version,
                published_at=candidate.published_at,
                last_observed_at=candidate.last_observed_at,
            )
            evaluation = evaluate_pair(listing, candidate, self.dedupe)
            if evaluation.method == "deterministic":
                return candidate
        return None

    def _maybe_geocode(self, fields: NormalizedFields) -> NormalizedFields:
        if fields.geometry is not None:
            return fields
        if self.geocoder is None:
            return fields
        if fields.geo_precision not in {"neighborhood", "unknown"}:
            return fields
        max_precision: str = (
            "neighborhood"
            if fields.neighborhood is not None and not fields.location_text
            else "block"
        )
        if not fields.location_text and fields.neighborhood is None:
            return fields
        result = self.geocoder.geocode(
            location_text=fields.location_text,
            neighborhood=fields.neighborhood,
            max_precision=max_precision,
        )
        if result.geometry is None:
            return fields
        precision: GeoPrecision = result.precision
        if _PRECISION_ORDER[precision] > _PRECISION_ORDER[max_precision]:
            precision = cast(GeoPrecision, max_precision)
        return NormalizedFields(
            operation=fields.operation,
            property_type=fields.property_type,
            price_value=fields.price_value,
            price_currency=fields.price_currency,
            expenses_value=fields.expenses_value,
            expenses_currency=fields.expenses_currency,
            total_cost=fields.total_cost,
            price_assumptions=fields.price_assumptions,
            surface_m2=fields.surface_m2,
            rooms=fields.rooms,
            bedrooms=fields.bedrooms,
            floor=fields.floor,
            amenities=fields.amenities,
            description_text=fields.description_text,
            location_text=fields.location_text,
            neighborhood=fields.neighborhood,
            geo_precision=precision,
            geometry=result.geometry,
            geo_source=result.source,
            url=fields.url,
            normalization_errors=fields.normalization_errors,
            title_text=fields.title_text,
            surface_covered_m2=fields.surface_covered_m2,
            bathrooms=fields.bathrooms,
            toilettes=fields.toilettes,
            parking_spaces=fields.parking_spaces,
            age_years=fields.age_years,
            disposition=fields.disposition,
            orientation=fields.orientation,
            media_urls=fields.media_urls,
        )


def _build_listing(
    *,
    snapshot_id: UUID,
    run_id: UUID,
    canonical_property_id: UUID,
    snapshot: object,
    fields: NormalizedFields,
    normalizer_version: str,
    listing_id: UUID,
) -> NormalizedListing:
    captured_at = getattr(snapshot, "captured_at")
    published_at = getattr(snapshot, "published_at")
    source = getattr(snapshot, "source")
    external_id = getattr(snapshot, "external_id")
    return NormalizedListing(
        listing_id=listing_id,
        canonical_property_id=canonical_property_id,
        run_id=run_id,
        snapshot_id=snapshot_id,
        source=source,
        external_id=external_id,
        url=fields.url,
        published_at=published_at,
        last_observed_at=captured_at,
        normalizer_version=normalizer_version,
        operation=fields.operation,
        property_type=fields.property_type,
        price_value=fields.price_value,
        price_currency=fields.price_currency,
        expenses_value=fields.expenses_value,
        expenses_currency=fields.expenses_currency,
        total_cost=fields.total_cost,
        price_assumptions=fields.price_assumptions,
        surface_m2=fields.surface_m2,
        rooms=fields.rooms,
        bedrooms=fields.bedrooms,
        floor=fields.floor,
        amenities=fields.amenities,
        description_text=fields.description_text,
        location_text=fields.location_text,
        neighborhood=fields.neighborhood,
        geo_precision=fields.geo_precision,
        geometry=fields.geometry,
        geo_source=fields.geo_source,
        normalization_errors=fields.normalization_errors,
        title_text=fields.title_text,
        surface_covered_m2=fields.surface_covered_m2,
        bathrooms=fields.bathrooms,
        toilettes=fields.toilettes,
        parking_spaces=fields.parking_spaces,
        age_years=fields.age_years,
        disposition=fields.disposition,
        orientation=fields.orientation,
        media_urls=fields.media_urls,
    )


def _listing_from_fields(
    fields: NormalizedFields,
    *,
    source: SourceIdentity,
    external_id: str,
    canonical_id: UUID,
    run_id: UUID,
    snapshot_id: UUID,
    normalizer_version: str,
    published_at: datetime | None,
    last_observed_at: datetime,
) -> NormalizedListing:
    return NormalizedListing(
        listing_id=uuid4(),
        canonical_property_id=canonical_id,
        run_id=run_id,
        snapshot_id=snapshot_id,
        source=source,
        external_id=external_id,
        url=fields.url,
        published_at=published_at,
        last_observed_at=last_observed_at,
        normalizer_version=normalizer_version,
        operation=fields.operation,
        property_type=fields.property_type,
        price_value=fields.price_value,
        price_currency=fields.price_currency,
        expenses_value=fields.expenses_value,
        expenses_currency=fields.expenses_currency,
        total_cost=fields.total_cost,
        price_assumptions=fields.price_assumptions,
        surface_m2=fields.surface_m2,
        rooms=fields.rooms,
        bedrooms=fields.bedrooms,
        floor=fields.floor,
        amenities=fields.amenities,
        description_text=fields.description_text,
        location_text=fields.location_text,
        neighborhood=fields.neighborhood,
        geo_precision=fields.geo_precision,
        geometry=fields.geometry,
        geo_source=fields.geo_source,
        normalization_errors=fields.normalization_errors,
        title_text=fields.title_text,
        surface_covered_m2=fields.surface_covered_m2,
        bathrooms=fields.bathrooms,
        toilettes=fields.toilettes,
        parking_spaces=fields.parking_spaces,
        age_years=fields.age_years,
        disposition=fields.disposition,
        orientation=fields.orientation,
        media_urls=fields.media_urls,
    )


def _ordered_pair(
    a: NormalizedListing, b: NormalizedListing
) -> tuple[NormalizedListing, NormalizedListing]:
    if a.listing_id < b.listing_id:
        return a, b
    return b, a


def _json_safe(value: object) -> object:
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return value
