"""Shared Postgres + object-storage backend for ingestion integration tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from tests.support.containers import ServiceConnection

from umbral.application.ingestion.import_contract import ContractSpec
from umbral.infrastructure.ingestion.contract_loader import load_contract_v1
from umbral.infrastructure.object_store.filesystem import FilesystemObjectStore

SessionFactory = Callable[[], Session]
IngestionBackend = tuple[SessionFactory, FilesystemObjectStore, ServiceConnection]


@pytest.fixture
def ingestion_contract() -> ContractSpec:
    return load_contract_v1()


@pytest.fixture
def ingestion_backend(
    request: pytest.FixtureRequest, tmp_path: Path
) -> IngestionBackend:
    """Postgres at head plus a filesystem object store for one test."""
    connection = request.getfixturevalue("postgres_container")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", connection.url)
    command.upgrade(config, "head")
    engine = create_engine(connection.url)
    factory = sessionmaker(engine, expire_on_commit=False)
    object_store = FilesystemObjectStore(str(tmp_path / "objects"))

    def teardown() -> None:
        engine.dispose()

    request.addfinalizer(teardown)
    return factory, object_store, connection
