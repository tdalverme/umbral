"""Shared Postgres backend and seeding for chat integration tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from itertools import count
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from tests.support.containers import ServiceConnection

from umbral.application.chat.service import ChatService
from umbral.application.radar.contracts import SearchProfile
from umbral.infrastructure.db.repositories.chat import (
    SqlAlchemyChatMessageRepository,
    SqlAlchemyChatSessionRepository,
    SqlAlchemySearchProfileStatusReader,
)
from umbral.infrastructure.db.repositories.radar import SqlAlchemyEventRepository
from umbral.infrastructure.radar.contract_loader import load_events_registry

SessionFactory = Callable[[], Session]

_NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
_tick = count()


def _advancing_clock() -> datetime:
    return _NOW + timedelta(seconds=next(_tick))


@pytest.fixture
def chat_backend(request: pytest.FixtureRequest) -> SessionFactory:
    """Postgres at head for one chat integration test."""
    connection: ServiceConnection = request.getfixturevalue("postgres_container")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", connection.url)
    command.upgrade(config, "head")
    engine = create_engine(connection.url)
    factory = sessionmaker(engine, expire_on_commit=False)

    def teardown() -> None:
        engine.dispose()

    request.addfinalizer(teardown)
    return factory


def build_chat(factory: SessionFactory) -> ChatService:
    return ChatService(
        sessions=SqlAlchemyChatSessionRepository(factory),
        messages=SqlAlchemyChatMessageRepository(factory),
        profile_status=SqlAlchemySearchProfileStatusReader(factory),
        events_out=SqlAlchemyEventRepository(factory),
        events_registry=load_events_registry(),
        max_message_length=4000,
        clock=_advancing_clock,
    )


def seed_user(factory: SessionFactory) -> UUID:
    from tests.integration.radar.conftest import seed_user as _seed_user

    return _seed_user(factory)


def seed_profile(factory: SessionFactory, owner_id: UUID) -> SearchProfile:
    from tests.support.radar import build_profile

    from umbral.application.radar.contracts import ProfileVersion
    from umbral.infrastructure.db.repositories.radar import (
        SqlAlchemyProfileVersionRepository,
        SqlAlchemySearchProfileRepository,
    )

    profile = build_profile(owner_id=owner_id, name="Mi radar")
    SqlAlchemySearchProfileRepository(factory).insert(profile)
    version = ProfileVersion(
        version_id=uuid4(),
        profile_id=profile.profile_id,
        profile_version=1,
        payload={},
        created_at=_NOW,
        correlation_id=uuid4(),
    )
    SqlAlchemyProfileVersionRepository(factory).insert(version)
    return profile
