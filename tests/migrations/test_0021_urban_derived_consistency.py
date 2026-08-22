"""Migration coverage for Urban geometry and snapshot-scoped lineage."""

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


def test_0021_supports_real_geometry_and_snapshot_scoped_signals(
    migration_postgres: ServiceConnection,
) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", migration_postgres.url)
    command.upgrade(config, "0020_silver_listing_attributes")
    command.upgrade(config, "0021_urban_derived_consistency")

    engine = create_engine(migration_postgres.url)
    with engine.connect() as connection:
        geometry_type = connection.execute(
            sa.text(
                "SELECT type FROM geometry_columns "
                "WHERE f_table_name = 'urban_categories' "
                "AND f_geometry_column = 'geometry'"
            )
        ).scalar_one()
        assert geometry_type == "GEOMETRY"

        nullable_counts = connection.execute(
            sa.text(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'urban_primitives' "
                "AND column_name IN ('count_300m', 'count_600m')"
            )
        ).all()
        assert {column: nullable for column, nullable in nullable_counts} == {
            "count_300m": "YES",
            "count_600m": "YES",
        }

        constraints = connection.execute(
            sa.text(
                "SELECT conname, pg_get_constraintdef(oid) "
                "FROM pg_constraint "
                "WHERE conrelid = 'urban_signals'::regclass "
                "AND contype = 'u'"
            )
        ).all()
        definitions = {str(name): str(definition) for name, definition in constraints}
        assert "uq_urban_signals_listing_snapshot_contract_signal" in definitions
        assert "uq_urban_signals_listing_contract_signal" not in definitions
        assert (
            "listing_id, snapshot_id, contract_version_id, signal"
            in definitions["uq_urban_signals_listing_snapshot_contract_signal"]
        )
    engine.dispose()
