"""Migration coverage for V5 command receipts."""

from __future__ import annotations

import os
from pathlib import Path
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


def test_0022_does_not_recreate_the_enum_after_explicit_creation() -> None:
    """The table column must reuse the enum created by the migration itself."""
    source = Path(
        "alembic/versions/0022_conversation_v5_command_receipts.py"
    ).read_text(encoding="utf-8")
    enum_declaration = source.split("receipt_state = postgresql.ENUM(", 1)[1].split(
        ")", 1
    )[0]

    assert "create_type=False" in enum_declaration


def test_0022_reuses_a_receipt_enum_that_exists_before_upgrade(
    migration_postgres: ServiceConnection,
) -> None:
    """A retried preview migration must not recreate its already-created enum."""
    config = _config(migration_postgres)
    command.upgrade(config, "0021_urban_derived_consistency")
    engine = create_engine(migration_postgres.url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TYPE conversation_v5_receipt_state "
                "AS ENUM ('started', 'applied', 'failed')"
            )
        )

    command.upgrade(config, "0022_conversation_v5_command_receipts")

    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text(
                    "SELECT to_regclass('conversation_v5_command_receipts')"
                )
            ).scalar_one()
            == "conversation_v5_command_receipts"
        )
    engine.dispose()
