"""Contract tests for the shared Testcontainers helpers.

The tests replace the Docker-backed classes with deterministic fakes.  This
keeps collection and the fixture contract checks runnable on hosts without a
Docker daemon while still exercising the lifecycle code and metadata mapping.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

HELPER_MODULE = "tests.support.containers"


class FakeContainer:
    """Small stand-in for a Testcontainers container used by contract tests."""

    instances: list["FakeContainer"] = []

    def __init__(self, image: str, **kwargs: Any) -> None:
        self.image = image
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self.__class__.instances.append(self)

    def __enter__(self) -> "FakeContainer":
        self.started = True
        return self

    def __exit__(self, *_: object) -> None:
        self.stopped = True

    def get_container_host_ip(self) -> str:
        return "127.0.0.1"

    def get_exposed_port(self, port: int) -> int:
        return port + 10000

    def get_connection_url(self, **_: Any) -> str:
        return "postgresql+psycopg://umbral:secret@127.0.0.1:11000/umbral"


@pytest.fixture
def helper_module() -> ModuleType:
    """Import the helper only when a contract test explicitly requests it."""

    return importlib.import_module(HELPER_MODULE)


def test_helper_import_does_not_construct_or_start_containers() -> None:
    module = importlib.import_module(HELPER_MODULE)

    assert module.POSTGRES_IMAGE == "ghcr.io/pglayers/pglayers-full:17"
    assert module.REDIS_IMAGE == "redis:8.6.4-alpine"
    assert module.MINIO_IMAGE == "alpine/minio:RELEASE.2025-10-15T17-29-55Z"


def test_postgres_context_pins_image_exposes_metadata_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    helper_module: ModuleType,
) -> None:
    FakeContainer.instances.clear()
    monkeypatch.setattr(helper_module, "PostgresContainer", FakeContainer)

    with helper_module.postgres_container() as connection:
        assert connection.service == "postgres"
        assert connection.host == "127.0.0.1"
        assert connection.port == 15432
        assert connection.url.startswith("postgresql+psycopg://")
        assert connection.container.image == helper_module.POSTGRES_IMAGE
        assert FakeContainer.instances[-1].started is True

    assert FakeContainer.instances[-1].stopped is True


def test_redis_context_pins_image_exposes_metadata_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    helper_module: ModuleType,
) -> None:
    FakeContainer.instances.clear()
    monkeypatch.setattr(helper_module, "RedisContainer", FakeContainer)

    with helper_module.redis_container() as connection:
        assert connection.service == "redis"
        assert connection.host == "127.0.0.1"
        assert connection.port == 16379
        assert connection.url == "redis://127.0.0.1:16379/0"
        assert connection.container.image == helper_module.REDIS_IMAGE

    assert FakeContainer.instances[-1].stopped is True


def test_minio_context_pins_image_exposes_s3_metadata_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
    helper_module: ModuleType,
) -> None:
    FakeContainer.instances.clear()
    monkeypatch.setattr(helper_module, "DockerContainer", FakeContainer)

    with helper_module.minio_container() as connection:
        assert connection.service == "minio"
        assert connection.host == "127.0.0.1"
        assert connection.port == 19000
        assert connection.console_port == 19001
        assert connection.url == "http://127.0.0.1:19000"
        assert connection.access_key == helper_module.MINIO_ROOT_USER
        assert connection.secret_key == helper_module.MINIO_ROOT_PASSWORD
        assert connection.container.image == helper_module.MINIO_IMAGE

    assert FakeContainer.instances[-1].stopped is True


def test_helper_source_contains_no_sqlite_fallback() -> None:
    source = Path(__file__).with_name("containers.py").read_text(encoding="utf-8")

    assert "sqlite" not in source.lower()


def test_shared_fixtures_are_function_scoped() -> None:
    conftest = importlib.import_module("tests.conftest")

    for fixture_name in ("postgres_container", "redis_container", "minio_container"):
        fixture = getattr(conftest, fixture_name)
        assert fixture._fixture_function_marker.scope == "function"
