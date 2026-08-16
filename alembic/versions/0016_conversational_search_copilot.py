"""Persist conversational preferences and partial radar state."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0016_conversational_search_copilot"
down_revision = "0015_observation_source_urban"
branch_labels = None
depends_on = None

_DOWNGRADE_REFUSAL = "0016 downgrade would invent required search constraints"


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _actor_kind() -> postgresql.ENUM:
    return postgresql.ENUM(name="actor_kind", create_type=False)


def _audit_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", _ts(), nullable=False),
        sa.Column("updated_at", _ts(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "actor_kind", _actor_kind(), nullable=False, server_default="system"
        ),
        sa.Column("actor_id", sa.String(128)),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
    ]


def _replace_run_state_type(values: tuple[str, ...]) -> None:
    old_type = "recommendation_run_state_0016_old"
    op.execute(f"ALTER TYPE recommendation_run_state RENAME TO {old_type}")
    literals = ", ".join(f"'{value}'" for value in values)
    op.execute(f"CREATE TYPE recommendation_run_state AS ENUM ({literals})")
    op.execute(
        "ALTER TABLE recommendation_runs "
        "ALTER COLUMN state TYPE recommendation_run_state "
        "USING state::text::recommendation_run_state"
    )
    op.execute(f"DROP TYPE {old_type}")


def _create_preference_tables() -> None:
    op.create_table(
        "preference_expressions",
        *_audit_columns(),
        sa.Column(
            "profile_id",
            _uuid(),
            sa.ForeignKey(
                "search_profiles.id",
                name="fk_preference_expressions_profile_id_search_profiles",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column(
            "source_message_id",
            _uuid(),
            sa.ForeignKey(
                "chat_messages.id",
                name="fk_preference_expressions_source_message_id_chat_messages",
                ondelete="SET NULL",
            ),
        ),
        sa.Column("source_kind", sa.String(30), nullable=False),
        sa.Column("subject_key", sa.String(100), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("authority", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "superseded_by",
            _uuid(),
            sa.ForeignKey(
                "preference_expressions.id",
                name=(
                    "fk_preference_expressions_superseded_by_"
                    "preference_expressions"
                ),
                ondelete="RESTRICT",
            ),
        ),
        sa.Column("original_text_available", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "source_kind IN ('chat', 'structured', 'feedback', 'suggestion', "
            "'migration')",
            name="ck_preference_expressions_source_kind",
        ),
        sa.CheckConstraint(
            "authority IN ('explicit', 'deliberate_feedback', 'passive')",
            name="ck_preference_expressions_authority",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded', 'withdrawn')",
            name="ck_preference_expressions_status",
        ),
        sa.CheckConstraint(
            "status = 'superseded' OR superseded_by IS NULL",
            name="ck_preference_expressions_superseded_shape",
        ),
    )
    op.create_index(
        "ix_preference_expressions_profile_status_created",
        "preference_expressions",
        ["profile_id", "status", "created_at"],
    )
    op.create_index(
        "ix_preference_expressions_profile_subject_status",
        "preference_expressions",
        ["profile_id", "subject_key", "status"],
    )
    op.create_index(
        "ix_preference_expressions_source_message",
        "preference_expressions",
        ["source_message_id"],
    )
    op.create_index(
        "ix_preference_expressions_superseded_by",
        "preference_expressions",
        ["superseded_by"],
    )

    op.create_table(
        "criterion_bindings",
        *_audit_columns(),
        sa.Column(
            "expression_id",
            _uuid(),
            sa.ForeignKey(
                "preference_expressions.id",
                name="fk_criterion_bindings_expression_id_preference_expressions",
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column(
            "concept_key",
            sa.String(100),
            sa.ForeignKey(
                "concepts.key",
                name="fk_criterion_bindings_concept_key_concepts",
                ondelete="RESTRICT",
            ),
        ),
        sa.Column("matcher_type", sa.String(50)),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False),
        sa.Column("limitations", postgresql.JSONB(), nullable=False),
        sa.Column("interpretation_version", sa.String(100), nullable=False),
        sa.Column("query_embedding", Vector(1536)),
        sa.Column(
            "embedding_version_id",
            _uuid(),
            sa.ForeignKey(
                "extraction_versions.id",
                name="fk_criterion_bindings_embedding_version_id_extraction_versions",
                ondelete="RESTRICT",
            ),
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "superseded_by",
            _uuid(),
            sa.ForeignKey(
                "criterion_bindings.id",
                name="fk_criterion_bindings_superseded_by_criterion_bindings",
                ondelete="RESTRICT",
            ),
        ),
        sa.CheckConstraint(
            "kind IN ('structured', 'semantic', 'unresolved', 'forbidden')",
            name="ck_criterion_bindings_kind",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_criterion_bindings_confidence",
        ),
        sa.CheckConstraint(
            "mode IN ('soft', 'hard')", name="ck_criterion_bindings_mode"
        ),
        sa.CheckConstraint(
            "kind <> 'semantic' OR mode = 'soft'",
            name="ck_criterion_bindings_semantic_soft",
        ),
        sa.CheckConstraint(
            "kind NOT IN ('unresolved', 'forbidden') OR concept_key IS NULL",
            name="ck_criterion_bindings_unbound_without_concept",
        ),
        sa.CheckConstraint(
            "kind <> 'structured' OR "
            "(concept_key IS NOT NULL AND matcher_type IS NOT NULL "
            "AND query_embedding IS NULL AND embedding_version_id IS NULL)",
            name="ck_criterion_bindings_structured_shape",
        ),
        sa.CheckConstraint(
            "kind <> 'semantic' OR "
            "(concept_key IS NULL AND matcher_type = 'semantic_feature' "
            "AND query_embedding IS NOT NULL AND embedding_version_id IS NOT NULL)",
            name="ck_criterion_bindings_semantic_shape",
        ),
        sa.CheckConstraint(
            "kind NOT IN ('unresolved', 'forbidden') OR "
            "(matcher_type IS NULL AND query_embedding IS NULL "
            "AND embedding_version_id IS NULL AND mode = 'soft')",
            name="ck_criterion_bindings_noncomputable_shape",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded')",
            name="ck_criterion_bindings_status",
        ),
        sa.CheckConstraint(
            "status = 'superseded' OR superseded_by IS NULL",
            name="ck_criterion_bindings_superseded_shape",
        ),
    )
    op.create_index(
        "ix_criterion_bindings_expression_status_created",
        "criterion_bindings",
        ["expression_id", "status", "created_at"],
    )
    op.create_index(
        "ix_criterion_bindings_expression_status_kind",
        "criterion_bindings",
        ["expression_id", "status", "kind"],
    )
    op.create_index(
        "ix_criterion_bindings_concept", "criterion_bindings", ["concept_key"]
    )
    op.create_index(
        "ix_criterion_bindings_embedding_version",
        "criterion_bindings",
        ["embedding_version_id"],
    )
    op.create_index(
        "ix_criterion_bindings_superseded_by",
        "criterion_bindings",
        ["superseded_by"],
    )


def _backfill_fact_lineage() -> None:
    op.execute(
        """INSERT INTO preference_expressions
        (id, created_at, updated_at, version, actor_kind, actor_id, source,
         correlation_id, profile_id, source_message_id, source_kind,
         subject_key, raw_text, authority, status, superseded_by,
         original_text_available)
        SELECT md5(pf.id::text || '-expression')::uuid,
               pf.created_at, pf.updated_at, pf.version, pf.actor_kind,
               pf.actor_id, 'migration.0016', pf.correlation_id, pf.profile_id,
               NULL, 'migration', pf.concept_key,
               pf.concept_key || '=' || pf.value::text, 'explicit',
               CASE WHEN pf.state = 'active' THEN 'active' ELSE 'superseded' END,
               CASE WHEN pf.superseded_by IS NULL THEN NULL
                    ELSE md5(pf.superseded_by::text || '-expression')::uuid END,
               false
        FROM preference_facts pf
        ORDER BY pf.id"""
    )
    op.execute(
        """INSERT INTO criterion_bindings
        (id, created_at, updated_at, version, actor_kind, actor_id, source,
         correlation_id, expression_id, kind, concept_key, matcher_type, mode,
         params, confidence, evidence_refs, limitations,
         interpretation_version, query_embedding, embedding_version_id,
         status, superseded_by)
        SELECT md5(pf.id::text || '-binding')::uuid,
               pf.created_at, pf.updated_at, pf.version, pf.actor_kind,
               pf.actor_id, 'migration.0016', pf.correlation_id,
               md5(pf.id::text || '-expression')::uuid,
               'structured', pf.concept_key, c.matcher_type, 'soft',
               jsonb_build_object('value', pf.value, 'weight', pf.weight,
                                  'polarity', pf.polarity),
               pf.confidence,
               jsonb_build_array(jsonb_build_object('kind', 'migration_fact',
                                                     'fact_id', pf.id::text)),
               '[]'::jsonb, 'migration-0016', NULL, NULL,
               CASE WHEN pf.state = 'active' THEN 'active' ELSE 'superseded' END,
               CASE WHEN pf.superseded_by IS NULL THEN NULL
                    ELSE md5(pf.superseded_by::text || '-binding')::uuid END
        FROM preference_facts pf
        JOIN concepts c ON c.key = pf.concept_key
        ORDER BY pf.id"""
    )
    op.execute(
        """UPDATE preference_facts
           SET criterion_binding_id = md5(id::text || '-binding')::uuid"""
    )


def upgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=False,
    )
    _create_preference_tables()
    op.add_column(
        "preference_facts",
        sa.Column("criterion_binding_id", _uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_preference_facts_criterion_binding_id_criterion_bindings",
        "preference_facts",
        "criterion_bindings",
        ["criterion_binding_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_preference_facts_criterion_binding",
        "preference_facts",
        ["criterion_binding_id"],
    )

    op.alter_column("chat_sessions", "search_profile_id", nullable=True)
    op.alter_column("search_profiles", "budget_max", nullable=True)
    op.alter_column("search_profiles", "min_rooms", nullable=True)
    op.drop_constraint(
        "ck_search_profiles_budget", "search_profiles", type_="check"
    )
    op.create_check_constraint(
        "ck_search_profiles_budget",
        "search_profiles",
        "(budget_max IS NULL OR budget_max > 0) "
        "AND (budget_min IS NULL OR budget_min >= 0) "
        "AND (budget_min IS NULL OR budget_max IS NULL "
        "OR budget_min < budget_max)",
    )

    op.drop_constraint(
        "ck_recommendation_runs_state_finished",
        "recommendation_runs",
        type_="check",
    )
    _replace_run_state_type(
        ("pending", "running", "succeeded", "failed", "superseded")
    )
    op.create_check_constraint(
        "ck_recommendation_runs_state_finished",
        "recommendation_runs",
        "state IN ('pending', 'running', 'succeeded', 'failed', 'superseded') "
        "AND (state IN ('pending', 'running') OR finished_at IS NOT NULL)",
    )
    op.add_column(
        "recommendation_runs",
        sa.Column(
            "diagnostics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    _backfill_fact_lineage()


def _downgrade_would_invent_constraints() -> bool:
    connection = op.get_bind()
    return bool(
        connection.scalar(
            sa.text(
                """SELECT EXISTS (
                    SELECT 1 FROM search_profiles
                    WHERE budget_max IS NULL OR min_rooms IS NULL
                ) OR EXISTS (
                    SELECT 1 FROM chat_sessions WHERE search_profile_id IS NULL
                ) OR EXISTS (
                    SELECT 1 FROM recommendation_runs WHERE state::text = 'superseded'
                )"""
            )
        )
    )


def downgrade() -> None:
    if _downgrade_would_invent_constraints():
        raise RuntimeError(_DOWNGRADE_REFUSAL)

    op.drop_column("recommendation_runs", "diagnostics")
    op.drop_constraint(
        "ck_recommendation_runs_state_finished",
        "recommendation_runs",
        type_="check",
    )
    _replace_run_state_type(("pending", "running", "succeeded", "failed"))
    op.create_check_constraint(
        "ck_recommendation_runs_state_finished",
        "recommendation_runs",
        "state IN ('pending', 'running', 'succeeded', 'failed') "
        "AND (state IN ('pending', 'running') OR finished_at IS NOT NULL)",
    )

    op.drop_constraint(
        "ck_search_profiles_budget", "search_profiles", type_="check"
    )
    op.create_check_constraint(
        "ck_search_profiles_budget",
        "search_profiles",
        "budget_max > 0 AND (budget_min IS NULL OR budget_min < budget_max)",
    )
    op.alter_column("search_profiles", "min_rooms", nullable=False)
    op.alter_column("search_profiles", "budget_max", nullable=False)
    op.alter_column("chat_sessions", "search_profile_id", nullable=False)

    op.drop_index(
        "ix_preference_facts_criterion_binding", table_name="preference_facts"
    )
    op.drop_constraint(
        "fk_preference_facts_criterion_binding_id_criterion_bindings",
        "preference_facts",
        type_="foreignkey",
    )
    op.drop_column("preference_facts", "criterion_binding_id")
    op.drop_table("criterion_bindings")
    op.drop_table("preference_expressions")
    # Alembic stamps the target revision only after downgrade() returns. The
    # current 0016 identifier is longer than 32 characters, so narrowing here
    # would fail before Alembic can write the shorter 0015 identifier.
