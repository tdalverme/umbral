"""SQLAlchemy repositories for Silver normalization; each method owns its commit."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from umbral.application.ingestion.contracts import SourceIdentity
from umbral.application.silver.contracts import (
    ACTIVE_NORMALIZER_VERSION,
    CanonicalProperty,
    CanonicalState,
    ChangeType,
    CurrencyType,
    DedupeLink,
    DedupeLinkState,
    DedupeMethod,
    GeoPrecision,
    ListingChange,
    NormalizedListing,
    OperationType,
    PropertyType,
)
from umbral.infrastructure.db.models.silver import (
    CanonicalProperty as CanonicalPropertyModel,
)
from umbral.infrastructure.db.models.silver import (
    DedupeLink as DedupeLinkModel,
)
from umbral.infrastructure.db.models.silver import (
    ListingChange as ListingChangeModel,
)
from umbral.infrastructure.db.models.silver import (
    SilverListing as SilverListingModel,
)

SessionFactory = Callable[[], Session]

ListingRow = tuple[SilverListingModel, Any, Any]


class SqlAlchemyCanonicalPropertyRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def create(
        self,
        *,
        canonical_property_id: UUID,
        first_seen_at: datetime,
        correlation_id: UUID,
        actor_kind: str,
        actor_id: str | None,
    ) -> CanonicalProperty:
        with self.session_factory() as session:
            model = CanonicalPropertyModel(
                id=canonical_property_id,
                created_at=first_seen_at,
                updated_at=first_seen_at,
                actor_kind=actor_kind,
                actor_id=actor_id,
                source="silver.normalize",
                correlation_id=correlation_id,
                state="active",
                first_seen_at=first_seen_at,
                latest_listing_id=None,
            )
            session.add(model)
            session.commit()
            return _to_domain_canonical(model)

    def get(self, canonical_property_id: UUID) -> CanonicalProperty | None:
        with self.session_factory() as session:
            model = session.get(CanonicalPropertyModel, canonical_property_id)
            return _to_domain_canonical(model) if model is not None else None


class SqlAlchemySilverListingRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert(self, listing: NormalizedListing) -> None:
        with self.session_factory() as session:
            model = SilverListingModel(
                id=listing.listing_id,
                created_at=listing.last_observed_at,
                updated_at=listing.last_observed_at,
                actor_kind="system",
                actor_id=None,
                source="silver.normalize",
                correlation_id=listing.run_id,
                canonical_property_id=listing.canonical_property_id,
                run_id=listing.run_id,
                snapshot_id=listing.snapshot_id,
                source_id=listing.source.source_id,
                source_version=listing.source.source_version,
                contract_version=listing.source.contract_version,
                external_id=listing.external_id,
                url=listing.url,
                published_at=listing.published_at,
                last_observed_at=listing.last_observed_at,
                normalizer_version=listing.normalizer_version,
                operation=listing.operation,
                property_type=listing.property_type,
                price_value=listing.price_value,
                price_currency=listing.price_currency,
                expenses_value=listing.expenses_value,
                expenses_currency=listing.expenses_currency,
                total_cost=listing.total_cost,
                price_assumptions=dict(listing.price_assumptions),
                title_text=listing.title_text,
                surface_m2=listing.surface_m2,
                surface_covered_m2=listing.surface_covered_m2,
                rooms=listing.rooms,
                bedrooms=listing.bedrooms,
                bathrooms=listing.bathrooms,
                toilettes=listing.toilettes,
                parking_spaces=listing.parking_spaces,
                floor=listing.floor,
                age_years=listing.age_years,
                disposition=listing.disposition,
                orientation=listing.orientation,
                amenities=list(listing.amenities),
                description_text=listing.description_text,
                media_urls=list(listing.media_urls),
                location_text=listing.location_text,
                neighborhood=listing.neighborhood,
                geo_precision=listing.geo_precision,
                geometry=_geometry_element(listing.geometry),
                geo_source=listing.geo_source,
                normalization_errors=list(listing.normalization_errors),
                captured_at=listing.last_observed_at,
            )
            session.add(model)
            session.commit()

    def get(self, listing_id: UUID) -> NormalizedListing | None:
        with self.session_factory() as session:
            row = _listing_row(session, SilverListingModel.id == listing_id)
            return _to_domain_listing(row) if row is not None else None

    def exists(self, *, snapshot_id: UUID, normalizer_version: str) -> bool:
        with self.session_factory() as session:
            row = session.scalar(
                select(SilverListingModel.id).where(
                    SilverListingModel.snapshot_id == snapshot_id,
                    SilverListingModel.normalizer_version == normalizer_version,
                )
            )
            return row is not None

    def list_chain(
        self, source_id: str, external_id: str
    ) -> tuple[NormalizedListing, ...]:
        with self.session_factory() as session:
            rows = _listing_rows(
                session,
                SilverListingModel.source_id == source_id,
                SilverListingModel.external_id == external_id,
                order_by=SilverListingModel.captured_at,
            )
            return tuple(_to_domain_listing(row) for row in rows)

    def list_canonical(
        self, canonical_property_id: UUID
    ) -> tuple[NormalizedListing, ...]:
        with self.session_factory() as session:
            rows = _listing_rows(
                session,
                SilverListingModel.canonical_property_id == canonical_property_id,
                order_by=SilverListingModel.captured_at,
            )
            return tuple(_to_domain_listing(row) for row in rows)

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
        with self.session_factory() as session:
            rows = _listing_rows(
                session,
                SilverListingModel.operation == operation,
                func.lower(SilverListingModel.neighborhood) == neighborhood.casefold(),
                SilverListingModel.normalizer_version == ACTIVE_NORMALIZER_VERSION,
                or_(
                    SilverListingModel.source_id != source_id,
                    SilverListingModel.external_id != external_id,
                ),
                order_by=SilverListingModel.captured_at,
            )
            return tuple(_to_domain_listing(row) for row in rows)

    def latest_for_source(
        self, source_id: str, external_id: str
    ) -> NormalizedListing | None:
        chain = self.list_chain(source_id, external_id)
        return chain[-1] if chain else None


class SqlAlchemyDedupeLinkRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert(self, link: DedupeLink) -> None:
        with self.session_factory() as session:
            model = DedupeLinkModel(
                id=link.link_id,
                created_at=link.created_at,
                updated_at=link.created_at,
                actor_kind="system",
                actor_id=None,
                source="silver.dedupe",
                correlation_id=link.listing_a_id,
                listing_a_id=link.listing_a_id,
                listing_b_id=link.listing_b_id,
                method=link.method,
                state=link.state,
                fingerprint=link.fingerprint,
                score=link.score,
                evidence=dict(link.evidence),
                decided_by=None,
                decided_at=None,
            )
            session.add(model)
            session.commit()

    def get(self, link_id: UUID) -> DedupeLink | None:
        with self.session_factory() as session:
            model = session.get(DedupeLinkModel, link_id)
            return _to_domain_link(model) if model is not None else None

    def find_pair(self, a_id: UUID, b_id: UUID) -> DedupeLink | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(DedupeLinkModel).where(
                    DedupeLinkModel.listing_a_id == a_id,
                    DedupeLinkModel.listing_b_id == b_id,
                )
            )
            return _to_domain_link(model) if model is not None else None

    def list_by_state(self, state: DedupeLinkState) -> tuple[DedupeLink, ...]:
        with self.session_factory() as session:
            models = session.scalars(
                select(DedupeLinkModel)
                .where(DedupeLinkModel.state == state)
                .order_by(DedupeLinkModel.created_at)
            )
            return tuple(_to_domain_link(model) for model in models)

    def save(self, link: DedupeLink) -> None:
        decided = link.decided_at or datetime.now(timezone.utc)
        with self.session_factory() as session:
            model = session.get(DedupeLinkModel, link.link_id)
            if model is None:
                raise KeyError(link.link_id)
            if model.version != link.version:
                raise DedupeLinkConflict(link.link_id)
            model.state = link.state
            model.decided_by = link.decided_by
            model.decided_at = decided
            model.updated_at = decided
            session.commit()


class SqlAlchemyChangeRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert(self, change: ListingChange) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            model = ListingChangeModel(
                id=change.change_id,
                created_at=now,
                updated_at=now,
                actor_kind="system",
                actor_id=None,
                source="silver.changes",
                correlation_id=change.listing_id,
                listing_id=change.listing_id,
                previous_listing_id=change.previous_listing_id,
                change_type=change.change_type,
                field=change.field,
                before=_json_value(change.before),
                after=_json_value(change.after),
                origin=dict(change.origin),
            )
            session.add(model)
            session.commit()

    def list_for_listing(self, listing_id: UUID) -> tuple[ListingChange, ...]:
        with self.session_factory() as session:
            models = session.scalars(
                select(ListingChangeModel)
                .where(ListingChangeModel.listing_id == listing_id)
                .order_by(ListingChangeModel.created_at)
            )
            return tuple(_to_domain_change(model) for model in models)

    def list_for_chain(
        self, source_id: str, external_id: str
    ) -> tuple[ListingChange, ...]:
        with self.session_factory() as session:
            listing_ids = session.scalars(
                select(SilverListingModel.id).where(
                    SilverListingModel.source_id == source_id,
                    SilverListingModel.external_id == external_id,
                )
            )
            ids = tuple(listing_ids)
            if not ids:
                return ()
            models = session.scalars(
                select(ListingChangeModel)
                .where(ListingChangeModel.listing_id.in_(ids))
                .order_by(ListingChangeModel.created_at)
            )
            return tuple(_to_domain_change(model) for model in models)


class DedupeLinkConflict(Exception):
    def __init__(self, link_id: UUID) -> None:
        self.link_id = link_id
        super().__init__(f"dedupe link version conflict: {link_id}")


def _geometry_element(geometry: tuple[float, float] | None) -> WKTElement | None:
    if geometry is None:
        return None
    lat, lon = geometry
    return WKTElement(f"SRID=4326;POINT({lon} {lat})")


def _listing_row(session: Session, *filters: Any) -> ListingRow | None:
    rows = _listing_rows(session, *filters)
    return rows[0] if rows else None


def _listing_rows(
    session: Session, *filters: Any, order_by: Any | None = None
) -> list[ListingRow]:
    statement = select(
        SilverListingModel,
        func.ST_Y(cast(Any, SilverListingModel.geometry)).label("geo_lat"),
        func.ST_X(cast(Any, SilverListingModel.geometry)).label("geo_lon"),
    ).where(*filters)
    if order_by is not None:
        statement = statement.order_by(order_by)
    rows = session.execute(statement).all()
    return [cast(ListingRow, tuple(row)) for row in rows]


def _to_domain_canonical(model: CanonicalPropertyModel) -> CanonicalProperty:
    return CanonicalProperty(
        canonical_property_id=model.id,
        state=cast(CanonicalState, model.state),
        first_seen_at=model.first_seen_at,
        latest_listing_id=model.latest_listing_id,
        version=model.version,
    )


def _to_domain_listing(row: ListingRow) -> NormalizedListing:
    model = row[0]
    lat = row[1]
    lon = row[2]
    geometry = (float(lat), float(lon)) if lat is not None and lon is not None else None
    return NormalizedListing(
        listing_id=model.id,
        canonical_property_id=model.canonical_property_id,
        run_id=model.run_id,
        snapshot_id=model.snapshot_id,
        source=SourceIdentity(
            source_id=model.source_id,
            source_version=model.source_version,
            contract_version=model.contract_version,
        ),
        external_id=model.external_id,
        url=model.url,
        published_at=model.published_at,
        last_observed_at=model.last_observed_at,
        normalizer_version=model.normalizer_version,
        operation=cast(OperationType, model.operation),
        property_type=cast(PropertyType, model.property_type),
        price_value=float(model.price_value),
        price_currency=cast(CurrencyType, model.price_currency),
        expenses_value=(
            float(model.expenses_value) if model.expenses_value is not None else None
        ),
        expenses_currency=cast(CurrencyType, model.expenses_currency),
        total_cost=float(model.total_cost),
        price_assumptions=dict(model.price_assumptions or {}),
        title_text=model.title_text,
        surface_m2=float(model.surface_m2) if model.surface_m2 is not None else None,
        surface_covered_m2=(
            float(model.surface_covered_m2)
            if model.surface_covered_m2 is not None
            else None
        ),
        rooms=model.rooms,
        bedrooms=model.bedrooms,
        bathrooms=(float(model.bathrooms) if model.bathrooms is not None else None),
        toilettes=(float(model.toilettes) if model.toilettes is not None else None),
        parking_spaces=(
            float(model.parking_spaces) if model.parking_spaces is not None else None
        ),
        floor=model.floor,
        age_years=(float(model.age_years) if model.age_years is not None else None),
        disposition=model.disposition,
        orientation=model.orientation,
        amenities=tuple(model.amenities or ()),
        description_text=model.description_text,
        media_urls=tuple(model.media_urls or ()),
        location_text=model.location_text,
        neighborhood=model.neighborhood,
        geo_precision=cast(GeoPrecision, model.geo_precision),
        geometry=geometry,
        geo_source=model.geo_source,
        normalization_errors=tuple(model.normalization_errors or ()),
    )


def _to_domain_link(model: DedupeLinkModel) -> DedupeLink:
    return DedupeLink(
        link_id=model.id,
        listing_a_id=model.listing_a_id,
        listing_b_id=model.listing_b_id,
        method=cast(DedupeMethod, model.method),
        state=cast(DedupeLinkState, model.state),
        fingerprint=model.fingerprint,
        score=float(model.score) if model.score is not None else None,
        evidence=dict(model.evidence or {}),
        created_at=model.created_at,
        version=model.version,
        decided_by=model.decided_by,
        decided_at=model.decided_at,
    )


def _to_domain_change(model: ListingChangeModel) -> ListingChange:
    return ListingChange(
        change_id=model.id,
        listing_id=model.listing_id,
        previous_listing_id=model.previous_listing_id,
        change_type=cast(ChangeType, model.change_type),
        field=model.field,
        before=model.before,
        after=model.after,
        origin=dict(model.origin or {}),
    )


def _json_value(value: object) -> object:
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value
