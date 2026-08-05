"""Shared backend matrix for durable-job contracts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tests.support.containers import ServiceConnection

from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.infrastructure.jobs.runtime import SqlAlchemyJobRuntime
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue

JobRuntimeFactory = Callable[
    [RecordingJobQueue], InMemoryJobRuntime | SqlAlchemyJobRuntime
]


@pytest.fixture(params=["memory", "sqlalchemy"], ids=["memory", "postgres"])
def job_runtime_factory(
    request: pytest.FixtureRequest,
) -> JobRuntimeFactory:
    if request.param == "memory":
        return lambda queue: InMemoryJobRuntime(queue=queue)

    postgres = request.getfixturevalue("postgres_container")
    assert isinstance(postgres, ServiceConnection)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgres.url)
    command.upgrade(config, "head")
    engine = create_engine(postgres.url)
    factory = sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)

    def create(queue: RecordingJobQueue) -> SqlAlchemyJobRuntime:
        return SqlAlchemyJobRuntime(factory, queue=queue, now=lambda: now)

    request.addfinalizer(engine.dispose)
    return create
