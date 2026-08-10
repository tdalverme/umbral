# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Shared Postgres backend and seeding for agent tools integration tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import count

from tests.integration.agent.conftest import (
    AgentStack,
    agent_backend,
    create_session,
    seed_profile,
    seed_user,
)

from umbral.application.chat.service import ChatService
from umbral.infrastructure.agent.composition import ChatScopeReader
from umbral.infrastructure.db.repositories.chat import (
    SqlAlchemyChatMessageRepository,
    SqlAlchemyChatSessionRepository,
    SqlAlchemySearchProfileStatusReader,
)
from umbral.infrastructure.db.repositories.radar import SqlAlchemyEventRepository
from umbral.infrastructure.radar.contract_loader import load_events_registry

__all__ = [
    "AgentStack",
    "agent_backend",
    "seed_user",
    "seed_profile",
    "create_session",
    "build_scope_stack",
    "ScopeStack",
]

_NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
_tick = count()


def _advancing_clock() -> datetime:
    return _NOW + timedelta(seconds=next(_tick))


@dataclass(frozen=True, slots=True)
class ScopeStack:
    chat: ChatService
    scope_reader: ChatScopeReader


def build_scope_stack(factory) -> ScopeStack:
    chat = ChatService(
        sessions=SqlAlchemyChatSessionRepository(factory),
        messages=SqlAlchemyChatMessageRepository(factory),
        profile_status=SqlAlchemySearchProfileStatusReader(factory),
        events_out=SqlAlchemyEventRepository(factory),
        events_registry=load_events_registry(),
        max_message_length=4000,
        clock=_advancing_clock,
    )
    return ScopeStack(chat=chat, scope_reader=ChatScopeReader(chat))
