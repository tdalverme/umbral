"""Silver normalization: canonical properties, listings, dedupe links, changes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base, IdentityAuditMixin

CANONICAL_STATE = ENUM("active", name="canonical_state", create_type=True)
OPERATION_TYPE = ENUM("rental", name="operation_type", create_type=True)
PROPERTY_TYPE = ENUM(
    "apartment",
    "house",
    "room",
    "studio",
    "commercial",
    "other",
    name="property_type",
    create_type=True,
)
CURRENCY_TYPE = ENUM("ARS", "USD", name="currency_type", create_type=True)
GEO_PRECISION = ENUM(
    "exact",
    "block",
    "neighborhood",
    "approximate",
    "unknown",
    name="geo_precision",
    create_type=True,
)
DEDUPE_METHOD = ENUM(
    "deterministic", "proposal", name="dedupe_method", create_type=True
)
DEDUPE_LINK_STATE = ENUM(
    "pending",
    "confirmed",
    "rejected",
    name="dedupe_link_state",
    create_type=True,
)
CHANGE_TYPE = ENUM(
    "price", "text", "attribute", "status", name="change_type", create_type=True
)


class CanonicalProperty(IdentityAuditMixin, Base):
    __tablename__ = "canonical_properties"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        CheckConstraint("state IN ('active')", name="ck_canonical_properties_state"),
    )

    state: Mapped[str] = mapped_column(
        CANONICAL_STATE, nullable=False, default="active"
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    latest_listing_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


class SilverListing(IdentityAuditMixin, Base):
    __tablename__ = "silver_listings"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "normalizer_version",
            name="uq_silver_listings_snapshot_version",
        ),
        UniqueConstraint(
            "source_id",
            "external_id",
            "captured_at",
            "normalizer_version",
            name="uq_silver_listings_source_external_captured",
        ),
        CheckConstraint("price_value > 0", name="ck_silver_listings_price"),
        CheckConstraint("total_cost > 0", name="ck_silver_listings_total_cost"),
        CheckConstraint(
            "expenses_value >= 0 OR expenses_value IS NULL",
            name="ck_silver_listings_expenses",
        ),
        CheckConstraint(
            "surface_m2 IS NULL OR (surface_m2 > 0 AND surface_m2 <= 1000000)",
            name="ck_silver_listings_surface",
        ),
        CheckConstraint(
            "rooms IS NULL OR (rooms >= 0 AND rooms <= 200)",
            name="ck_silver_listings_rooms",
        ),
        CheckConstraint(
            "bedrooms IS NULL OR (bedrooms >= 0 AND bedrooms <= 100)",
            name="ck_silver_listings_bedrooms",
        ),
        CheckConstraint(
            "floor IS NULL OR (floor >= -10 AND floor <= 1000)",
            name="ck_silver_listings_floor",
        ),
        Index(
            "ix_silver_listings_canonical_captured",
            "canonical_property_id",
            "captured_at",
        ),
        Index(
            "ix_silver_listings_source_external_captured_idx",
            "source_id",
            "external_id",
            "captured_at",
        ),
        Index("ix_silver_listings_geo_precision", "geo_precision"),
        Index(
            "ix_silver_listings_operation_type_currency",
            "operation",
            "property_type",
            "price_currency",
        ),
    )

    canonical_property_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("canonical_properties.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("import_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("raw_listing_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source_version: Mapped[str] = mapped_column(String(100), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    normalizer_version: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(OPERATION_TYPE, nullable=False)
    property_type: Mapped[str] = mapped_column(PROPERTY_TYPE, nullable=False)
    price_value: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    price_currency: Mapped[str] = mapped_column(CURRENCY_TYPE, nullable=False)
    expenses_value: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    expenses_currency: Mapped[str | None] = mapped_column(CURRENCY_TYPE, nullable=True)
    total_cost: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    price_assumptions: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    surface_m2: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    rooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amenities: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    description_text: Mapped[str | None] = mapped_column(String(20000), nullable=True)
    location_text: Mapped[str] = mapped_column(String(500), nullable=False)
    neighborhood: Mapped[str | None] = mapped_column(String(200), nullable=True)
    geo_precision: Mapped[str] = mapped_column(GEO_PRECISION, nullable=False)
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    geo_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    normalization_errors: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class DedupeLink(IdentityAuditMixin, Base):
    __tablename__ = "dedupe_links"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint("listing_a_id", "listing_b_id", name="uq_dedupe_links_pair"),
        CheckConstraint(
            "listing_a_id < listing_b_id", name="ck_dedupe_links_pair_order"
        ),
        CheckConstraint(
            "(method = 'deterministic' AND state = 'confirmed') OR "
            "(method = 'proposal')",
            name="ck_dedupe_links_state_method",
        ),
        CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1)",
            name="ck_dedupe_links_score",
        ),
        Index("ix_dedupe_links_state", "state"),
    )

    listing_a_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("silver_listings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    listing_b_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("silver_listings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    method: Mapped[str] = mapped_column(DEDUPE_METHOD, nullable=False)
    state: Mapped[str] = mapped_column(DEDUPE_LINK_STATE, nullable=False)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ListingChange(IdentityAuditMixin, Base):
    __tablename__ = "listing_changes"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint("listing_id", "field", name="uq_listing_changes_field"),
        Index("ix_listing_changes_previous", "previous_listing_id"),
        Index("ix_listing_changes_type_created", "change_type", "created_at"),
    )

    listing_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("silver_listings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    previous_listing_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    change_type: Mapped[str] = mapped_column(CHANGE_TYPE, nullable=False)
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    before: Mapped[object] = mapped_column(JSONB, nullable=False)
    after: Mapped[object] = mapped_column(JSONB, nullable=False)
    origin: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
