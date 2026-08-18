# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type"
"""Migration coverage for declarative urban signals."""

from __future__ import annotations

import os
from typing import cast

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


def test_0017_creates_urban_tables_and_adds_urban_kind(
    migration_postgres: ServiceConnection,
) -> None:
    config = _config(migration_postgres)
    command.upgrade(config, "0016_conversational_search_copilot")
    engine = create_engine(migration_postgres.url)
    with engine.connect() as connection:
        kind = connection.execute(
            sa.text("SELECT enum_range(NULL::extraction_kind)::text")
        ).scalar()
        # Before 0017 the urban kind is not yet present.
        assert "urban" not in (kind or "")
    command.upgrade(config, "0017_urban_signals")
    with engine.connect() as connection:
        kind_after = connection.execute(
            sa.text("SELECT enum_range(NULL::extraction_kind)::text")
        ).scalar()
        assert "urban" in (kind_after or "")
        tables = {
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public'"
                )
            )
        }
        assert {
            "urban_contracts",
            "urban_snapshots",
            "urban_categories",
            "urban_primitives",
            "urban_signals",
            "neighborhood_signal_stats",
        } <= tables
        # Listing observations remain intact and accept urban source.
        observation_sources = connection.execute(
            sa.text("SELECT enum_range(NULL::observation_source)::text")
        ).scalar()
        assert "urban" in (observation_sources or "")
        # urban_categories carries a PostGIS point for distance computation.
        geometry_columns = connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM geometry_columns "
                "WHERE f_table_name = 'urban_categories' "
                "AND type = 'POINT'"
            )
        ).scalar()
        assert geometry_columns == 1
    engine.dispose()


def test_0017_downgrade_refuses_when_urban_data_exists(
    migration_postgres: ServiceConnection,
) -> None:
    config = _config(migration_postgres)
    command.upgrade(config, "0017_urban_signals")
    engine = create_engine(migration_postgres.url)
    with engine.connect() as connection:
        connection.execute(
            sa.text(
                """INSERT INTO urban_contracts
                (id, created_at, updated_at, version, actor_kind, actor_id,
                 source, correlation_id, contract_version, payload, status)
                VALUES
                (gen_random_uuid(), now(), now(), 1, 'service', NULL,
                 'test', gen_random_uuid(), 'urban-contract-v1',
                 '{}'::jsonb, 'active')"""
            )
        )
        connection.commit()
    with pytest.raises(
        RuntimeError, match="0017 downgrade would discard urban signal data"
    ):
        command.downgrade(config, "0016_conversational_search_copilot")
    engine.dispose()


def test_0017_downgrade_succeeds_without_urban_data(
    migration_postgres: ServiceConnection,
) -> None:
    config = _config(migration_postgres)
    command.upgrade(config, "0017_urban_signals")
    engine = create_engine(migration_postgres.url)
    engine.dispose()

    command.downgrade(config, "0016_conversational_search_copilot")

    check_engine = create_engine(migration_postgres.url)
    with check_engine.connect() as connection:
        urban_contracts = connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM pg_tables WHERE tablename = 'urban_contracts'"
            )
        ).scalar()
        assert urban_contracts == 0
    check_engine.dispose()