# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type"
"""Migration coverage for the hard/soft catalog (soft_to_hard on facts)."""

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


def test_0018_adds_soft_to_hard_with_safe_default(
    migration_postgres: ServiceConnection,
) -> None:
    config = _config(migration_postgres)
    command.upgrade(config, "0017_urban_signals")
    engine = create_engine(migration_postgres.url)
    with engine.connect() as connection:
        column = connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name = 'preference_facts' "
                "AND column_name = 'soft_to_hard'"
            )
        ).scalar()
        assert column == 0
    command.upgrade(config, "0018_hard_soft_catalog")
    with engine.connect() as connection:
        column_after = connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name = 'preference_facts' "
                "AND column_name = 'soft_to_hard'"
            )
        ).scalar()
        assert column_after == 1
        default_is_false = connection.execute(
            sa.text(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name = 'preference_facts' "
                "AND column_name = 'soft_to_hard'"
            )
        ).scalar()
        assert default_is_false is not None
        assert "false" in (default_is_false or "").lower()
    engine.dispose()


def test_0018_downgrade_drops_the_column(
    migration_postgres: ServiceConnection,
) -> None:
    config = _config(migration_postgres)
    command.upgrade(config, "0018_hard_soft_catalog")
    command.downgrade(config, "0017_urban_signals")
    engine = create_engine(migration_postgres.url)
    with engine.connect() as connection:
        column = connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name = 'preference_facts' "
                "AND column_name = 'soft_to_hard'"
            )
        ).scalar()
        assert column == 0
    engine.dispose()
