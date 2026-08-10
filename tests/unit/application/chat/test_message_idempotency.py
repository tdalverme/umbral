"""Idempotent chat send and session listing (R-06, R-08; FR-024)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from tests.support.chat import (
    FixedProfileStatusReader,
    InMemoryChatMessageRepository,
    InMemoryChatSessionRepository,
    RecordingEventWriter,
)

from umbral.application.chat.service import ChatService
from umbral.infrastructure.radar.contract_loader import load_events_registry

_NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


def _build_service() -> tuple[ChatService, InMemoryChatMessageRepository]:
    messages = InMemoryChatMessageRepository()
    service = ChatService(
        sessions=InMemoryChatSessionRepository(),
        messages=messages,
        profile_status=FixedProfileStatusReader(),
        events_out=RecordingEventWriter(),
        events_registry=load_events_registry(),
        max_message_length=4000,
        clock=lambda: _NOW,
    )
    return service, messages


def test_replay_with_same_client_message_id_does_not_duplicate() -> None:
    service, messages = _build_service()
    user_id = uuid4()
    session = service.create_session(
        user_id=user_id, search_profile_id=uuid4(), correlation_id=uuid4(), now=_NOW
    )
    client_id = uuid4()
    first = service.append_user_message(
        user_id=user_id,
        session_id=session.session_id,
        text="quiero bajar el presupuesto",
        correlation_id=uuid4(),
        now=_NOW,
        client_message_id=client_id,
    )
    second = service.append_user_message(
        user_id=user_id,
        session_id=session.session_id,
        text="quiero bajar el presupuesto",
        correlation_id=uuid4(),
        now=_NOW,
        client_message_id=client_id,
    )
    assert second.message_id == first.message_id
    assert len(messages.list_by_session(session.session_id)) == 1


def test_different_client_ids_append_separate_messages() -> None:
    service, messages = _build_service()
    user_id = uuid4()
    session = service.create_session(
        user_id=user_id, search_profile_id=uuid4(), correlation_id=uuid4(), now=_NOW
    )
    first = service.append_user_message(
        user_id=user_id,
        session_id=session.session_id,
        text="mensaje uno",
        correlation_id=uuid4(),
        now=_NOW,
        client_message_id=uuid4(),
    )
    second = service.append_user_message(
        user_id=user_id,
        session_id=session.session_id,
        text="mensaje dos",
        correlation_id=uuid4(),
        now=_NOW,
        client_message_id=uuid4(),
    )
    assert first.message_id != second.message_id
    assert len(messages.list_by_session(session.session_id)) == 2


def test_list_sessions_returns_profile_sessions_newest_first() -> None:
    service, _messages = _build_service()
    user_id = uuid4()
    profile_id = uuid4()
    first = service.create_session(
        user_id=user_id, search_profile_id=profile_id, correlation_id=uuid4()
    )
    second = service.create_session(
        user_id=user_id, search_profile_id=profile_id, correlation_id=uuid4()
    )
    sessions = service.list_sessions(user_id=user_id, search_profile_id=profile_id)
    assert [s.session_id for s in sessions] == [second.session_id, first.session_id]
    other = service.list_sessions(user_id=user_id, search_profile_id=uuid4())
    assert other == ()
