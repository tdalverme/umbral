"""Shared pytest fixtures for real service integration tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timezone

import pytest
import pytest_asyncio

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


@pytest_asyncio.fixture
async def identity_now() -> AsyncIterator[datetime]:
    """Stable async clock fixture for identity API/browser-boundary tests."""

    yield datetime(2026, 1, 1, tzinfo=timezone.utc)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark identity paths so CI can run the focused slice deterministically."""

    marker = pytest.mark.identity
    for item in items:
        if "identity" in item.nodeid:
            item.add_marker(marker)
