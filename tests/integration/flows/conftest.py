"""Postgres fixture for the cross-domain SPEC validation flow."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from tests.support.containers import ServiceConnection

SessionFactory = Callable[[], Session]


@pytest.fixture
def spec_validation_backend(
    request: pytest.FixtureRequest,
) -> SessionFactory:
    connection: ServiceConnection = request.getfixturevalue("postgres_container")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", connection.url)
    command.upgrade(config, "head")
    engine = create_engine(connection.url)
    factory = sessionmaker(engine, expire_on_commit=False)
    request.addfinalizer(engine.dispose)
    return factory
