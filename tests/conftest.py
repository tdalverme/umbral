"""Shared pytest fixtures for real service integration tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from tests.support import containers


@pytest.fixture(scope="function")
def postgres_container() -> Iterator[containers.ServiceConnection]:
    """A fresh PostgreSQL service container for one test."""

    with containers.postgres_container() as connection:
        yield connection


@pytest.fixture(scope="function")
def redis_container() -> Iterator[containers.ServiceConnection]:
    """A fresh Redis service container for one test."""

    with containers.redis_container() as connection:
        yield connection


@pytest.fixture(scope="function")
def minio_container() -> Iterator[containers.ServiceConnection]:
    """A fresh MinIO service container for one test."""

    with containers.minio_container() as connection:
        yield connection
