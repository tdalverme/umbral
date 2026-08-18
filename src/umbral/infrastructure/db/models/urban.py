"""Durable entities for declarative urban signals."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base, IdentityAuditMixin


class UrbanContract(IdentityAuditMixin, Base):
    """The active declarative urban contract."""

    __tablename__ = "urban_contracts"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint("contract_version", name="uq_urban_contracts_version"),
        CheckConstraint(
            "status IN ('active', 'superseded')",
            name="ck_urban_contracts_status",
        ),
        CheckConstraint(
            "pg_column_size(payload::text) <= 65536",
            name="ck_urban_contracts_payload_size",
        ),
    )

    contract_version: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    superseded_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("urban_contracts.id", ondelete="RESTRICT"),
        nullable=True,
    )


class UrbanSnapshot(IdentityAuditMixin, Base):
    """One immutable OSM data snapshot."""

    __tablename__ = "urban_snapshots"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        CheckConstraint(
            "status IN ('importing', 'ready', 'failed')",
            name="ck_urban_snapshots_status",
        ),
        Index("ix_urban_snapshots_status_created", "status", "created_at"),
    )

    source_path: Mapped[str] = mapped_column(String(512), nullable=False)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    data_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="importing")
    poi_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    linear_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class UrbanCategory(IdentityAuditMixin, Base):
    """A category derived from the tags mapping, for one snapshot."""

    __tablename__ = "urban_categories"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "osm_id",
            "category",
            name="uq_urban_categories_snapshot_osm",
        ),
        CheckConstraint(
            "kind IN ('poi', 'linear')", name="ck_urban_categories_kind"
        ),
        Index("ix_urban_categories_snapshot_kind", "snapshot_id", "kind"),
        Index("ix_urban_categories_category", "category"),
        Index(
            "ix_urban_categories_snapshot_geom",
            "snapshot_id",
            "geometry",
            postgresql_using="gist",
        ),
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("urban_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    osm_id: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )


class UrbanPrimitive(IdentityAuditMixin, Base):
    """Aggregated raw metrics per listing and category."""

    __tablename__ = "urban_primitives"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "listing_id",
            "snapshot_id",
            "category",
            name="uq_urban_primitives_listing_snapshot_category",
        ),
        CheckConstraint(
            "kind IN ('poi', 'linear')", name="ck_urban_primitives_kind"
        ),
        Index("ix_urban_primitives_listing_snapshot", "listing_id", "snapshot_id"),
        Index("ix_urban_primitives_category", "category"),
    )

    listing_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("silver_listings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("urban_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    count_300m: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    count_600m: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nearest_m: Mapped[float | None] = mapped_column(Float, nullable=True)


class UrbanSignal(IdentityAuditMixin, Base):
    """One factual signal per listing, with raw and normalized values."""

    __tablename__ = "urban_signals"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "listing_id",
            "contract_version_id",
            "signal",
            name="uq_urban_signals_listing_contract_signal",
        ),
        CheckConstraint(
            "value >= 0 AND value <= 1", name="ck_urban_signals_value"
        ),
        CheckConstraint(
            "normalized_value IS NULL OR "
            "(normalized_value >= 0 AND normalized_value <= 1)",
            name="ck_urban_signals_normalized_value",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_urban_signals_confidence"
        ),
        CheckConstraint(
            "normalization_scope IN ('barrio', 'caba')",
            name="ck_urban_signals_scope",
        ),
        Index("ix_urban_signals_listing_contract", "listing_id", "contract_version_id"),
        Index("ix_urban_signals_snapshot", "snapshot_id"),
        Index("ix_urban_signals_signal", "signal"),
    )

    listing_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("silver_listings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("urban_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    contract_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("urban_contracts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    signal: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    normalized_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalization_scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default="barrio"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    missing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    contributors: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )


class NeighborhoodSignalStats(IdentityAuditMixin, Base):
    """Precomputed percentiles per barrio and signal."""

    __tablename__ = "neighborhood_signal_stats"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "barrio",
            "signal",
            name="uq_neighborhood_stats_snapshot_barrio_signal",
        ),
        CheckConstraint(
            "normalization_scope IN ('barrio', 'caba')",
            name="ck_neighborhood_stats_scope",
        ),
        CheckConstraint(
            "sample_size >= 0", name="ck_neighborhood_stats_sample_size"
        ),
        Index("ix_neighborhood_stats_barrio_signal", "barrio", "signal"),
    )

    snapshot_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("urban_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    barrio: Mapped[str] = mapped_column(String(100), nullable=False)
    signal: Mapped[str] = mapped_column(String(100), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    normalization_scope: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    p75: Mapped[float | None] = mapped_column(Float, nullable=True)
    p90: Mapped[float | None] = mapped_column(Float, nullable=True)
