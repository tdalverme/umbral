"""Migration coverage for durable conversational preference lineage."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from io import StringIO
from typing import cast
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine

from tests.support.containers import ServiceConnection


@pytest.fixture
def migration_postgres(request: pytest.FixtureRequest) -> ServiceConnection:
    external_url = os.getenv("UMBRAL_TEST_POSTGRES_URL")
    if external_url:
        return ServiceConnection(
            service="postgres",
            host="127.0.0.1",
            port=5432,
            url=external_url,
            container=None,
        )
    connection = request.getfixturevalue("postgres_container")
    return cast(ServiceConnection, connection)


def _config(connection: ServiceConnection) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", connection.url)
    return config


def _audit_values(*, row_id: UUID | None = None) -> dict[str, object]:
    now = datetime(2026, 8, 14, tzinfo=timezone.utc)
    return {
        "id": row_id or uuid4(),
        "created_at": now,
        "updated_at": now,
        "version": 1,
        "actor_kind": "service",
        "actor_id": None,
        "source": "migration-test",
        "correlation_id": uuid4(),
    }


def _seed_legacy_fact(connection: sa.Connection) -> UUID:
    user = _audit_values()
    user.update(
        normalized_email=f"migration-{user['id']}@example.invalid",
        email_normalization_version=1,
        status="active",
        disabled_reason=None,
        status_changed_at=user["created_at"],
        status_changed_by_user_id=None,
        status_change_source="migration-test",
    )
    connection.execute(
        sa.text(
            """INSERT INTO product_users
            (id, created_at, updated_at, version, actor_kind, actor_id, source,
             correlation_id, normalized_email, email_normalization_version,
             status, disabled_reason, status_changed_at,
             status_changed_by_user_id, status_change_source)
            VALUES
            (:id, :created_at, :updated_at, :version, :actor_kind, :actor_id,
             :source, :correlation_id, :normalized_email,
             :email_normalization_version, :status, :disabled_reason,
             :status_changed_at, :status_changed_by_user_id,
             :status_change_source)"""
        ),
        user,
    )
    profile = _audit_values()
    profile.update(
        owner_id=user["id"],
        name="Legacy",
        operation="rental",
        zones=["palermo"],
        budget_max=1000,
        budget_min=None,
        min_rooms=1,
        surface_min=None,
        surface_max=None,
        status="active",
        unknown_strategy={},
        current_version_id=None,
        latest_run_id=None,
    )
    connection.execute(
        sa.text(
            """INSERT INTO search_profiles
            (id, created_at, updated_at, version, actor_kind, actor_id, source,
             correlation_id, owner_id, name, operation, zones, budget_max,
             budget_min, min_rooms, surface_min, surface_max, status,
             unknown_strategy, current_version_id, latest_run_id)
            VALUES
            (:id, :created_at, :updated_at, :version, :actor_kind, :actor_id,
             :source, :correlation_id, :owner_id, :name, :operation,
             CAST(:zones AS jsonb), :budget_max, :budget_min, :min_rooms,
             :surface_min, :surface_max, :status,
             CAST(:unknown_strategy AS jsonb), :current_version_id,
             :latest_run_id)"""
        ),
        {**profile, "zones": '["palermo"]', "unknown_strategy": "{}"},
    )
    concept = _audit_values()
    concept.update(
        key="balcon",
        name="Balcón",
        aliases="[]",
        matcher_type="categorical",
        params_schema="{}",
        defaults="{}",
        compute_policy="{}",
        current_version_id=None,
    )
    connection.execute(
        sa.text(
            """INSERT INTO concepts
            (id, created_at, updated_at, version, actor_kind, actor_id, source,
             correlation_id, key, name, aliases, matcher_type, params_schema,
             defaults, compute_policy, current_version_id)
            VALUES
            (:id, :created_at, :updated_at, :version, :actor_kind, :actor_id,
             :source, :correlation_id, :key, :name, CAST(:aliases AS jsonb),
             :matcher_type, CAST(:params_schema AS jsonb),
             CAST(:defaults AS jsonb), CAST(:compute_policy AS jsonb),
             :current_version_id)"""
        ),
        concept,
    )
    fact = _audit_values()
    fact.update(
        profile_id=profile["id"],
        concept_key="balcon",
        value='"si"',
        weight=1,
        polarity="positive",
        confidence=1,
        fact_source="legacy",
        state="active",
        superseded_by=None,
    )
    connection.execute(
        sa.text(
            """INSERT INTO preference_facts
            (id, created_at, updated_at, version, actor_kind, actor_id, source,
             correlation_id, profile_id, concept_key, value, weight, polarity,
             confidence, fact_source, state, superseded_by)
            VALUES
            (:id, :created_at, :updated_at, :version, :actor_kind, :actor_id,
             :source, :correlation_id, :profile_id, :concept_key,
             CAST(:value AS jsonb), :weight, :polarity, :confidence,
             :fact_source, :state, :superseded_by)"""
        ),
        fact,
    )
    connection.commit()
    return fact["id"]  # type: ignore[return-value]


def test_0016_backfills_fact_lineage(
    migration_postgres: ServiceConnection,
) -> None:
    config = _config(migration_postgres)
    command.upgrade(config, "0015_observation_source_urban")
    engine = create_engine(migration_postgres.url)
    with engine.connect() as connection:
        fact_id = _seed_legacy_fact(connection)
    command.upgrade(config, "0016_conversational_search_copilot")
    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                """SELECT pf.criterion_binding_id, pe.source_kind,
                          pe.original_text_available, pe.raw_text
                   FROM preference_facts pf
                   JOIN criterion_bindings cb ON cb.id = pf.criterion_binding_id
                   JOIN preference_expressions pe ON pe.id = cb.expression_id
                   WHERE pf.id = :fact_id"""
            ),
            {"fact_id": fact_id},
        ).one()
    engine.dispose()
    assert row.criterion_binding_id is not None
    assert row.source_kind == "migration"
    assert row.original_text_available is False
    assert row.raw_text == 'balcon="si"'


def test_0016_offline_sql_preserves_deterministic_backfill_suffixes() -> None:
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)

    command.upgrade(
        config,
        "0015_observation_source_urban:0016_conversational_search_copilot",
        sql=True,
    )

    rendered = output.getvalue()
    assert "md5(pf.id::text || '-expression')::uuid" in rendered
    assert "md5(pf.id::text || '-binding')::uuid" in rendered
    assert "md5(pf.id::text || 'NULL')::uuid" not in rendered


def test_0016_downgrade_refuses_to_invent_partial_profile_constraints(
    migration_postgres: ServiceConnection,
) -> None:
    config = _config(migration_postgres)
    command.upgrade(config, "0016_conversational_search_copilot")
    engine = create_engine(migration_postgres.url)
    with engine.connect() as connection:
        fact_id = _seed_legacy_fact(connection)
        assert fact_id is not None
        connection.execute(
            sa.text("UPDATE search_profiles SET budget_max = NULL")
        )
        connection.commit()

    with pytest.raises(
        RuntimeError,
        match="0016 downgrade would invent required search constraints",
    ):
        command.downgrade(config, "0015_observation_source_urban")
    engine.dispose()
