"""Shared Postgres backend and agent runtime stack for agent integration tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import count
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from tests.support.containers import ServiceConnection

from umbral.agent.graph import build_topology_v1
from umbral.agent.runtime import ChatRuntime
from umbral.application.agent.ports import ModelGateway
from umbral.application.agent.service import RunRecorderService
from umbral.application.chat.contracts import ChatSession
from umbral.application.chat.service import ChatService
from umbral.application.radar.contracts import SearchProfile
from umbral.infrastructure.agent.checkpointer import (
    create_postgres_saver,
)
from umbral.infrastructure.agent.model_gateway.fake import FakeModelGateway
from umbral.infrastructure.db.repositories.agent import (
    SqlAlchemyGraphRunRepository,
    SqlAlchemyModelCallRepository,
    SqlAlchemyNodeRunRepository,
)
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


REPLY_SCHEMA = {
    "reply_text": {"kind": "string", "min_length": 1, "max_length": 2000},
    "refs": {"kind": "list"},
}


@dataclass(frozen=True, slots=True)
class AgentStack:
    runtime: ChatRuntime
    chat: ChatService
    recorder: RunRecorderService
    runs: SqlAlchemyGraphRunRepository
    factory: SessionFactory


@pytest.fixture
def agent_backend(
    request: pytest.FixtureRequest,
) -> tuple[SessionFactory, str]:
    """Postgres at head for one agent integration test."""
    connection: ServiceConnection = request.getfixturevalue("postgres_container")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", connection.url)
    command.upgrade(config, "head")
    engine = create_engine(connection.url)
    factory = sessionmaker(engine, expire_on_commit=False)

    def teardown() -> None:
        engine.dispose()

    request.addfinalizer(teardown)
    return factory, connection.url


def build_stack(
    factory: SessionFactory, url: str, *, gateway: ModelGateway | None = None
) -> AgentStack:
    chat = ChatService(
        sessions=SqlAlchemyChatSessionRepository(factory),
        messages=SqlAlchemyChatMessageRepository(factory),
        profile_status=SqlAlchemySearchProfileStatusReader(factory),
        events_out=SqlAlchemyEventRepository(factory),
        events_registry=load_events_registry(),
        max_message_length=4000,
        clock=_advancing_clock,
    )
    runs = SqlAlchemyGraphRunRepository(factory)
    recorder = RunRecorderService(
        graph_runs=runs,
        node_runs=SqlAlchemyNodeRunRepository(factory),
        model_calls=SqlAlchemyModelCallRepository(factory),
    )
    saver = create_postgres_saver(url, strict_msgpack=True)
    graph = build_topology_v1(
        gateway=gateway or FakeModelGateway(),
        conversation=chat,
        recorder=recorder,
        saver=saver,
        clock=_advancing_clock,
        model_version="local-fake",
        prompt_version="agent-chat-v1",
        schema_version="reply-v1",
        reply_schema=REPLY_SCHEMA,
    )
    runtime = ChatRuntime(
        graph=graph,
        conversation=chat,
        runs=runs,
        recorder=recorder,
        clock=_advancing_clock,
    )
    return AgentStack(
        runtime=runtime,
        chat=chat,
        recorder=recorder,
        runs=runs,
        factory=factory,
    )


def seed_user(factory: SessionFactory) -> UUID:
    from tests.integration.radar.conftest import seed_user as _seed_user

    return cast(UUID, _seed_user(factory))


def seed_profile(factory: SessionFactory, owner_id: UUID) -> SearchProfile:
    from tests.integration.chat.conftest import seed_profile as _seed_profile

    return _seed_profile(factory, owner_id)


def create_session(factory: SessionFactory, owner_id: UUID) -> ChatSession:
    from tests.integration.chat.conftest import build_chat

    profile = seed_profile(factory, owner_id)
    chat = build_chat(factory)
    return chat.create_session(
        user_id=owner_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
