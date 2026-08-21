# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type"
"""Migration coverage for structured concept feedback (0019)."""

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


def _columns(engine: sa.Engine, name: str) -> tuple[str, ...]:
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'feedback_event_reasons' "
                "AND column_name = :name"
            ),
            {"name": name},
        )
        return tuple(row[0] for row in rows)


def test_0019_adds_strength_and_confidence_columns(
    migration_postgres: ServiceConnection,
) -> None:
    config = _config(migration_postgres)
    command.upgrade(config, "0018_hard_soft_catalog")
    engine = create_engine(migration_postgres.url)
    assert _columns(engine, "strength") == ()
    assert _columns(engine, "confidence") == ()
    command.upgrade(config, "0019_feedback_strength_confidence")
    assert _columns(engine, "strength") == ("strength",)
    assert _columns(engine, "confidence") == ("confidence",)
    engine.dispose()


def test_0019_strength_enum_accepts_declared_values(
    migration_postgres: ServiceConnection,
) -> None:
    config = _config(migration_postgres)
    command.upgrade(config, "0019_feedback_strength_confidence")
    engine = create_engine(migration_postgres.url)
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT enumlabel FROM pg_enum WHERE enumtypid = "
                "(SELECT oid FROM pg_type WHERE typname = 'feedback_strength')"
            )
        )
        labels = tuple(row[0] for row in rows)
    assert labels == ("low", "medium", "strong")
    engine.dispose()


def test_0019_downgrade_drops_columns_and_enum(
    migration_postgres: ServiceConnection,
) -> None:
    config = _config(migration_postgres)
    command.upgrade(config, "0019_feedback_strength_confidence")
    command.downgrade(config, "0018_hard_soft_catalog")
    engine = create_engine(migration_postgres.url)
    assert _columns(engine, "strength") == ()
    assert _columns(engine, "confidence") == ()
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM pg_type WHERE typname = 'feedback_strength'"
            )
        )
        assert rows.scalar() == 0
    engine.dispose()