"""Criteria and observations schema: concepts, facts, compilations, observations."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0006_criteria_observations"
down_revision = "0005_search_radar"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _enum(name: str) -> postgresql.ENUM:
    values = {
        "actor_kind": ("system", "service", "operator"),
        "fact_state": ("active", "superseded"),
        "observation_state": ("active", "invalidated", "superseded", "failed"),
        "observation_source": ("rule", "model"),
        "extraction_kind": ("rule", "prompt", "schema", "model", "embedding"),
        "recompute_scope": ("concept", "extraction", "parser", "full"),
        "recompute_run_state": ("pending", "running", "succeeded", "failed"),
    }[name]
    return postgresql.ENUM(*values, name=name, create_type=False)


def _audit_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", _ts(), nullable=False),
        sa.Column("updated_at", _ts(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "actor_kind", _enum("actor_kind"), nullable=False, server_default="system"
        ),
        sa.Column("actor_id", sa.String(128)),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
    ]


def _audit_columns_with_source(
    source_column: postgresql.ENUM,
) -> list[sa.Column[object]]:
    """Audit columns whose ``source`` column carries the domain provenance enum."""

    columns = _audit_columns()
    for column in columns:
        if column.name == "source":
            columns[columns.index(column)] = sa.Column(
                "source", source_column, nullable=False
            )
    return columns


def _create_types() -> None:
    op.execute("CREATE TYPE fact_state AS ENUM ('active', 'superseded')")
    op.execute(
        "CREATE TYPE observation_state AS ENUM "
        "('active', 'invalidated', 'superseded', 'failed')"
    )
    op.execute("CREATE TYPE observation_source AS ENUM ('rule', 'model')")
    op.execute(
        "CREATE TYPE extraction_kind AS ENUM "
        "('rule', 'prompt', 'schema', 'model', 'embedding')"
    )
    op.execute(
        "CREATE TYPE recompute_scope AS ENUM "
        "('concept', 'extraction', 'parser', 'full')"
    )
    op.execute(
        "CREATE TYPE recompute_run_state AS ENUM "
        "('pending', 'running', 'succeeded', 'failed')"
    )


def _drop_types() -> None:
    for name in (
        "recompute_run_state",
        "recompute_scope",
        "extraction_kind",
        "observation_source",
        "observation_state",
        "fact_state",
    ):
        op.execute(f"DROP TYPE IF EXISTS {name}")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    _create_types()

    op.create_table(
        "concepts",
        *_audit_columns(),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("aliases", postgresql.JSONB(), nullable=False),
        sa.Column("matcher_type", sa.String(50), nullable=False),
        sa.Column("params_schema", postgresql.JSONB(), nullable=False),
        sa.Column("defaults", postgresql.JSONB(), nullable=False),
        sa.Column("compute_policy", postgresql.JSONB(), nullable=False),
        sa.Column("current_version_id", _uuid()),
        sa.UniqueConstraint("key", name="uq_concepts_key"),
        sa.CheckConstraint(
            "key ~ '^[a-z][a-z0-9_]{0,99}$'", name="ck_concepts_key_format"
        ),
        sa.CheckConstraint(
            "jsonb_array_length(aliases) <= 20", name="ck_concepts_aliases"
        ),
    )
    op.create_table(
        "concept_versions",
        *_audit_columns(),
        sa.Column(
            "concept_id",
            _uuid(),
            sa.ForeignKey("concepts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("concept_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "concept_id",
            "concept_version",
            name="uq_concept_versions_concept_version",
        ),
        sa.CheckConstraint(
            "concept_version >= 1", name="ck_concept_versions_concept_version"
        ),
    )
    op.create_table(
        "preference_facts",
        *_audit_columns(),
        sa.Column(
            "profile_id",
            _uuid(),
            sa.ForeignKey("search_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("concept_key", sa.String(100), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("weight", sa.Numeric(6, 4), nullable=False),
        sa.Column("polarity", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=False),
        sa.Column("fact_source", sa.String(50), nullable=False),
        sa.Column("state", _enum("fact_state"), nullable=False),
        sa.Column("superseded_by", _uuid()),
        sa.CheckConstraint(
            "weight >= 0 AND weight <= 1", name="ck_preference_facts_weight"
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_preference_facts_confidence"
        ),
        sa.CheckConstraint(
            "polarity IN ('positive', 'negative')", name="ck_preference_facts_polarity"
        ),
        sa.Index(
            "uq_preference_facts_active",
            "profile_id",
            "concept_key",
            unique=True,
            postgresql_where=sa.text("state = 'active'"),
        ),
        sa.Index("ix_preference_facts_profile_concept", "profile_id", "concept_key"),
        sa.Index("ix_preference_facts_profile_created", "profile_id", "created_at"),
    )
    op.create_table(
        "profile_criteria_compilations",
        *_audit_columns(),
        sa.Column(
            "profile_id",
            _uuid(),
            sa.ForeignKey("search_profiles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "profile_version_id",
            _uuid(),
            sa.ForeignKey("search_profile_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("compilation_version", sa.Integer(), nullable=False),
        sa.Column("criteria", postgresql.JSONB(), nullable=False),
        sa.Column("warnings", postgresql.JSONB(), nullable=False),
        sa.Column("confirmations", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "profile_version_id",
            "compilation_version",
            name="uq_criteria_compilations_profile_version_version",
        ),
        sa.Index(
            "ix_criteria_compilations_profile_created", "profile_id", "created_at"
        ),
        sa.Index("ix_criteria_compilations_profile_version", "profile_version_id"),
    )
    op.create_table(
        "extraction_versions",
        *_audit_columns(),
        sa.Column("kind", _enum("extraction_kind"), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("artifact_version", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint(
            "kind",
            "key",
            "artifact_version",
            name="uq_extraction_versions_kind_key_version",
        ),
        sa.CheckConstraint(
            "pg_column_size(payload::text) <= 65536",
            name="ck_extraction_versions_payload_size",
        ),
    )
    op.create_table(
        "recomputation_runs",
        *_audit_columns(),
        sa.Column("scope_kind", _enum("recompute_scope"), nullable=False),
        sa.Column("scope_key", sa.String(200)),
        sa.Column("cause", sa.String(200), nullable=False),
        sa.Column("state", _enum("recompute_run_state"), nullable=False),
        sa.Column("counts", postgresql.JSONB(), nullable=False),
        sa.Column("job_execution_id", _uuid()),
        sa.Column("finished_at", _ts()),
        sa.CheckConstraint(
            "scope_kind <> 'full' OR scope_key IS NOT NULL",
            name="ck_recompute_runs_scope_key",
        ),
        sa.Index("ix_recompute_runs_scope", "scope_kind", "scope_key"),
        sa.Index("ix_recompute_runs_created", "created_at"),
        sa.Index("ix_recompute_runs_state", "state"),
    )
    op.create_table(
        "listing_observations",
        *_audit_columns_with_source(_enum("observation_source")),
        sa.Column(
            "listing_id",
            _uuid(),
            sa.ForeignKey("silver_listings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("concept_key", sa.String(100), nullable=False),
        sa.Column("matcher_type", sa.String(50), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("score", sa.Numeric(6, 4), nullable=False),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column(
            "extraction_version_id",
            _uuid(),
            sa.ForeignKey("extraction_versions.id", ondelete="RESTRICT"),
        ),
        sa.Column("state", _enum("observation_state"), nullable=False),
        sa.Column("failure_code", sa.String(100)),
        sa.Column(
            "recomputation_run_id",
            _uuid(),
            sa.ForeignKey("recomputation_runs.id", ondelete="RESTRICT"),
        ),
        sa.CheckConstraint(
            "score >= 0 AND score <= 1", name="ck_listing_observations_score"
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_listing_observations_confidence",
        ),
        sa.CheckConstraint(
            "state <> 'failed' OR failure_code IS NOT NULL",
            name="ck_listing_observations_state_failure",
        ),
        sa.Index(
            "uq_listing_observations_active",
            "listing_id",
            "concept_key",
            "source",
            unique=True,
            postgresql_where=sa.text("state = 'active'"),
        ),
        sa.Index(
            "ix_listing_observations_listing_concept", "listing_id", "concept_key"
        ),
        sa.Index("ix_listing_observations_concept_state", "concept_key", "state"),
        sa.Index("ix_listing_observations_extraction_version", "extraction_version_id"),
        sa.Index("ix_listing_observations_state", "state"),
    )
    op.create_table(
        "listing_embeddings",
        *_audit_columns(),
        sa.Column(
            "listing_id",
            _uuid(),
            sa.ForeignKey("silver_listings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "extraction_version_id",
            _uuid(),
            sa.ForeignKey("extraction_versions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("state", _enum("observation_state"), nullable=False),
        sa.Column(
            "recomputation_run_id",
            _uuid(),
            sa.ForeignKey("recomputation_runs.id", ondelete="RESTRICT"),
        ),
        sa.Index(
            "uq_listing_embeddings_active",
            "listing_id",
            "extraction_version_id",
            unique=True,
            postgresql_where=sa.text("state = 'active'"),
        ),
        sa.Index("ix_listing_embeddings_listing", "listing_id"),
        sa.Index("ix_listing_embeddings_version", "extraction_version_id"),
    )
    op.create_table(
        "urban_signals",
        *_audit_columns(),
        sa.Column(
            "listing_id",
            _uuid(),
            sa.ForeignKey("silver_listings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("signal_type", sa.String(50), nullable=False),
        sa.Column("signal_source", sa.String(100), nullable=False),
        sa.Column("observed_at", _ts(), nullable=False),
        sa.Column(
            "geometry",
            Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("algorithm_version", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "signal_type IN ('cafe', 'transport', 'green_space')",
            name="ck_urban_signals_signal_type",
        ),
        sa.Index("ix_urban_signals_listing", "listing_id"),
        sa.Index("ix_urban_signals_type_observed", "signal_type", "observed_at"),
    )


def downgrade() -> None:
    for name in (
        "urban_signals",
        "listing_embeddings",
        "listing_observations",
        "recomputation_runs",
        "extraction_versions",
        "profile_criteria_compilations",
        "preference_facts",
        "concept_versions",
        "concepts",
    ):
        op.drop_table(name)
    _drop_types()
