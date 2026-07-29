"""Function-scoped Testcontainers helpers for integration tests.

Only the context managers in this module create containers.  Importing it is
safe during pytest collection and does not contact Docker.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Literal

from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import HttpWaitStrategy

POSTGRES_IMAGE = "ghcr.io/pglayers/pglayers-full:17"
REDIS_IMAGE = "redis:8.6.4-alpine"
MINIO_IMAGE = "alpine/minio:RELEASE.2025-10-15T17-29-55Z"

POSTGRES_PORT = 5432
REDIS_PORT = 6379
MINIO_PORT = 9000
MINIO_CONSOLE_PORT = 9001

POSTGRES_USER = "umbral"
POSTGRES_PASSWORD = "umbral_local_only"
POSTGRES_DATABASE = "umbral"
MINIO_ROOT_USER = "minio_local"
MINIO_ROOT_PASSWORD = "minio_local_password"

ServiceName = Literal["postgres", "redis", "minio"]


@dataclass(frozen=True, slots=True)
class ServiceConnection:
    """Connection metadata for a running test service and its container."""

    service: ServiceName
    host: str
    port: int
    url: str
    container: Any
    console_port: int | None = None
    username: str | None = None
    password: str | None = None
    database: str | None = None
    access_key: str | None = None
    secret_key: str | None = None

    @property
    def connection_url(self) -> str:
        """Alias used by adapters that call all endpoints connection URLs."""

        return self.url


@contextmanager
def postgres_container() -> Iterator[ServiceConnection]:
    """Start a pinned PostgreSQL container for one test and remove it after."""

    container = PostgresContainer(
        image=POSTGRES_IMAGE,
        username=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        dbname=POSTGRES_DATABASE,
        driver="psycopg",
    )
    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(POSTGRES_PORT)
        yield ServiceConnection(
            service="postgres",
            host=host,
            port=port,
            url=container.get_connection_url(driver="psycopg"),
            container=container,
            username=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            database=POSTGRES_DATABASE,
        )


@contextmanager
def redis_container() -> Iterator[ServiceConnection]:
    """Start a pinned Redis container for one test and remove it after."""

    container = RedisContainer(image=REDIS_IMAGE)
    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(REDIS_PORT)
        yield ServiceConnection(
            service="redis",
            host=host,
            port=port,
            url=f"redis://{host}:{port}/0",
            container=container,
        )


@contextmanager
def minio_container() -> Iterator[ServiceConnection]:
    """Start a pinned MinIO S3-compatible container for one test and remove it."""

    container = DockerContainer(
        image=MINIO_IMAGE,
        command="server /data --console-address :9001",
        env={
            "MINIO_ROOT_USER": MINIO_ROOT_USER,
            "MINIO_ROOT_PASSWORD": MINIO_ROOT_PASSWORD,
        },
        ports=[MINIO_PORT, MINIO_CONSOLE_PORT],
        _wait_strategy=HttpWaitStrategy(MINIO_PORT, "/minio/health/ready"),
    )
    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(MINIO_PORT)
        console_port = container.get_exposed_port(MINIO_CONSOLE_PORT)
        yield ServiceConnection(
            service="minio",
            host=host,
            port=port,
            url=f"http://{host}:{port}",
            container=container,
            console_port=console_port,
            access_key=MINIO_ROOT_USER,
            secret_key=MINIO_ROOT_PASSWORD,
        )
