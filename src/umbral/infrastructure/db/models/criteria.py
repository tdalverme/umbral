"""Criteria and observations: concepts, facts, compilations, observations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
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

FACT_STATE = ENUM("active", "superseded", name="fact_state", create_type=True)
OBSERVATION_STATE = ENUM(
    "active",
    "invalidated",
    "superseded",
    "failed",
    name="observation_state",
    create_type=True,
)
OBSERVATION_SOURCE = ENUM(
    "rule",
    "model",
    "urban",
    name="observation_source",
    create_type=True,
)
EXTRACTION_KIND = ENUM(
    "rule",
    "prompt",
    "schema",
    "model",
    "embedding",
    name="extraction_kind",
    create_type=True,
)
RECOMPUTE_SCOPE = ENUM(
    "concept",
    "extraction",
    "parser",
    "full",
    name="recompute_scope",
    create_type=True,
)
RECOMPUTE_RUN_STATE = ENUM(
    "pending",
    "running",
    "succeeded",
    "failed",
    name="recompute_run_state",
    create_type=True,
)


class Concept(IdentityAuditMixin, Base):
    __tablename__ = "concepts"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint("key", name="uq_concepts_key"),
        CheckConstraint(
            "key ~ '^[a-z][a-z0-9_]{0,99}$'", name="ck_concepts_key_format"
        ),
        CheckConstraint(
            "jsonb_array_length(aliases) <= 20", name="ck_concepts_aliases"
        ),
    )

    key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    matcher_type: Mapped[str] = mapped_column(String(50), nullable=False)
    params_schema: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    defaults: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    compute_policy: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    current_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )


class ConceptVersion(IdentityAuditMixin, Base):
    __tablename__ = "concept_versions"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "concept_id",
            "concept_version",
            name="uq_concept_versions_concept_version",
        ),
        CheckConstraint(
            "concept_version >= 1", name="ck_concept_versions_concept_version"
        ),
    )

    concept_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("concepts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    concept_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class PreferenceFact(IdentityAuditMixin, Base):
    __tablename__ = "preference_facts"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        Index(
            "uq_preference_facts_active",
            "profile_id",
            "concept_key",
            postgresql_where="state = 'active'",
            unique=True,
        ),
        CheckConstraint(
            "weight >= 0 AND weight <= 1", name="ck_preference_facts_weight"
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_preference_facts_confidence"
        ),
        CheckConstraint(
            "polarity IN ('positive', 'negative')", name="ck_preference_facts_polarity"
        ),
        Index("ix_preference_facts_profile_concept", "profile_id", "concept_key"),
        Index("ix_preference_facts_profile_created", "profile_id", "created_at"),
        Index("ix_preference_facts_criterion_binding", "criterion_binding_id"),
    )

    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    concept_key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[object] = mapped_column(JSONB, nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    polarity: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    fact_source: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[str] = mapped_column(FACT_STATE, nullable=False, default="active")
    superseded_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    criterion_binding_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("criterion_bindings.id", ondelete="RESTRICT"),
        nullable=True,
    )


class ProfileCriteriaCompilation(IdentityAuditMixin, Base):
    __tablename__ = "profile_criteria_compilations"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "profile_version_id",
            "compilation_version",
            name="uq_criteria_compilations_profile_version_version",
        ),
        Index("ix_criteria_compilations_profile_created", "profile_id", "created_at"),
        Index("ix_criteria_compilations_profile_version", "profile_version_id"),
    )

    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    profile_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("search_profile_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    compilation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    criteria: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    confirmations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )


class ExtractionVersion(IdentityAuditMixin, Base):
    __tablename__ = "extraction_versions"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        UniqueConstraint(
            "kind",
            "key",
            "artifact_version",
            name="uq_extraction_versions_kind_key_version",
        ),
        CheckConstraint(
            "pg_column_size(payload::text) <= 65536",
            name="ck_extraction_versions_payload_size",
        ),
    )

    kind: Mapped[str] = mapped_column(EXTRACTION_KIND, nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    artifact_version: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )


class ListingObservation(IdentityAuditMixin, Base):
    __tablename__ = "listing_observations"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        Index(
            "uq_listing_observations_active",
            "listing_id",
            "concept_key",
            "source",
            postgresql_where="state = 'active'",
            unique=True,
        ),
        CheckConstraint(
            "score >= 0 AND score <= 1", name="ck_listing_observations_score"
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_listing_observations_confidence",
        ),
        CheckConstraint(
            "state <> 'failed' OR failure_code IS NOT NULL",
            name="ck_listing_observations_state_failure",
        ),
        Index("ix_listing_observations_listing_concept", "listing_id", "concept_key"),
        Index("ix_listing_observations_concept_state", "concept_key", "state"),
        Index("ix_listing_observations_extraction_version", "extraction_version_id"),
        Index("ix_listing_observations_state", "state"),
    )

    listing_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("silver_listings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    concept_key: Mapped[str] = mapped_column(String(100), nullable=False)
    matcher_type: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[object] = mapped_column(JSONB, nullable=False)
    score: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(6, 4), nullable=False)
    evidence: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    source: Mapped[str] = mapped_column(OBSERVATION_SOURCE, nullable=False)
    extraction_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("extraction_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    state: Mapped[str] = mapped_column(
        OBSERVATION_STATE, nullable=False, default="active"
    )
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recomputation_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("recomputation_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )


class RecomputeRun(IdentityAuditMixin, Base):
    __tablename__ = "recomputation_runs"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        CheckConstraint(
            "scope_kind <> 'full' OR scope_key IS NOT NULL",
            name="ck_recompute_runs_scope_key",
        ),
        Index("ix_recompute_runs_scope", "scope_kind", "scope_key"),
        Index("ix_recompute_runs_created", "created_at"),
        Index("ix_recompute_runs_state", "state"),
    )

    scope_kind: Mapped[str] = mapped_column(RECOMPUTE_SCOPE, nullable=False)
    scope_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cause: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(
        RECOMPUTE_RUN_STATE, nullable=False, default="pending"
    )
    counts: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    job_execution_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ListingEmbedding(IdentityAuditMixin, Base):
    __tablename__ = "listing_embeddings"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        Index(
            "uq_listing_embeddings_active",
            "listing_id",
            "extraction_version_id",
            postgresql_where="state = 'active'",
            unique=True,
        ),
        Index("ix_listing_embeddings_listing", "listing_id"),
        Index("ix_listing_embeddings_version", "extraction_version_id"),
    )

    listing_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("silver_listings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    extraction_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("extraction_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)
    state: Mapped[str] = mapped_column(
        OBSERVATION_STATE, nullable=False, default="active"
    )
    recomputation_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("recomputation_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )


class UrbanSignal(IdentityAuditMixin, Base):
    __tablename__ = "urban_signals"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        CheckConstraint(
            "signal_type IN ('cafe', 'transport', 'green_space')",
            name="ck_urban_signals_signal_type",
        ),
        Index("ix_urban_signals_listing", "listing_id"),
        Index("ix_urban_signals_type_observed", "signal_type", "observed_at"),
    )

    listing_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("silver_listings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    signal_source: Mapped[str] = mapped_column(String(100), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    geometry: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True
    )
    algorithm_version: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
