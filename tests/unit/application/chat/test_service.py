"""Chat service unit tests (US1, SC-001)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from tests.support.chat import (
    FixedProfileStatusReader,
    InMemoryChatMessageRepository,
    InMemoryChatSessionRepository,
    RecordingEventWriter,
)

from umbral.application.chat.contracts import (
    ChatMessageTooLong,
    ChatSessionNotActive,
    ChatSessionNotFound,
)
from umbral.application.chat.service import ChatService
from umbral.infrastructure.radar.contract_loader import load_events_registry

_NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def _build_service(
    *, statuses: dict[UUID, str] | None = None, max_length: int = 50
) -> tuple[ChatService, RecordingEventWriter]:
    events = RecordingEventWriter()
    service = ChatService(
        sessions=InMemoryChatSessionRepository(),
        messages=InMemoryChatMessageRepository(),
        profile_status=FixedProfileStatusReader(statuses),
        events_out=events,
        events_registry=load_events_registry(),
        max_message_length=max_length,
        clock=lambda: _NOW,
    )
    return service, events


def test_create_session_mirrors_profile_and_emits_event() -> None:
    service, events = _build_service()
    user_id = uuid4()
    profile_id = uuid4()
    session = service.create_session(
        user_id=user_id,
        search_profile_id=profile_id,
        correlation_id=uuid4(),
        now=_NOW,
    )
    assert session.user_id == user_id
    assert session.search_profile_id == profile_id
    assert session.status == "active"
    created = [e for e in events.events if e.event_type == "chat.session_created.v1"]
    assert len(created) == 1
    assert created[0].payload["session_id"] == str(session.session_id)
    assert created[0].payload["search_profile_id"] == str(profile_id)


def test_create_session_reflects_paused_profile() -> None:
    profile_id = uuid4()
    service, _events = _build_service(statuses={profile_id: "paused"})
    session = service.create_session(
        user_id=uuid4(), search_profile_id=profile_id, correlation_id=uuid4()
    )
    assert session.status == "paused"


def test_get_session_is_ownership_scoped() -> None:
    service, _events = _build_service()
    owner = uuid4()
    session = service.create_session(
        user_id=owner, search_profile_id=uuid4(), correlation_id=uuid4()
    )
    with pytest.raises(ChatSessionNotFound):
        service.get_session(user_id=uuid4(), session_id=session.session_id)
    assert service.get_session(user_id=owner, session_id=session.session_id) is not None


def test_assert_accepts_turn_rejects_paused_session() -> None:
    profile_id = uuid4()
    service, _events = _build_service(statuses={profile_id: "archived"})
    session = service.create_session(
        user_id=uuid4(), search_profile_id=profile_id, correlation_id=uuid4()
    )
    with pytest.raises(ChatSessionNotActive):
        service.assert_accepts_turn(
            user_id=session.user_id, session_id=session.session_id
        )


def test_append_user_message_persists_and_emits() -> None:
    service, events = _build_service()
    session = service.create_session(
        user_id=uuid4(), search_profile_id=uuid4(), correlation_id=uuid4()
    )
    message = service.append_user_message(
        user_id=session.user_id,
        session_id=session.session_id,
        text="hola",
        correlation_id=uuid4(),
    )
    assert message.role == "user"
    assert message.graph_run_id is None
    emitted = [e for e in events.events if e.event_type == "chat.message_created.v1"]
    assert len(emitted) == 1
    assert emitted[0].payload["message_id"] == str(message.message_id)
    assert emitted[0].payload["role"] == "user"


def test_append_user_message_rejects_too_long() -> None:
    service, _events = _build_service(max_length=5)
    session = service.create_session(
        user_id=uuid4(), search_profile_id=uuid4(), correlation_id=uuid4()
    )
    with pytest.raises(ChatMessageTooLong):
        service.append_user_message(
            user_id=session.user_id,
            session_id=session.session_id,
            text="hola mundo",
            correlation_id=uuid4(),
        )


def test_persist_assistant_message_links_run_and_emits() -> None:
    service, events = _build_service()
    session = service.create_session(
        user_id=uuid4(), search_profile_id=uuid4(), correlation_id=uuid4()
    )
    run_id = uuid4()
    message = service.persist_assistant_message(
        user_id=session.user_id,
        session_id=session.session_id,
        text="respuesta",
        refs=(),
        graph_run_id=run_id,
        correlation_id=uuid4(),
    )
    assert message.role == "assistant"
    assert message.graph_run_id == run_id
    emitted = [e for e in events.events if e.event_type == "chat.message_created.v1"]
    assert len(emitted) == 1
    assert emitted[0].payload["role"] == "assistant"


def test_history_is_ordered_and_immutable() -> None:
    service, _events = _build_service()
    session = service.create_session(
        user_id=uuid4(), search_profile_id=uuid4(), correlation_id=uuid4()
    )
    first = service.append_user_message(
        user_id=session.user_id,
        session_id=session.session_id,
        text="uno",
        correlation_id=uuid4(),
    )
    second = service.append_user_message(
        user_id=session.user_id,
        session_id=session.session_id,
        text="dos",
        correlation_id=uuid4(),
    )
    history = service.list_history(
        user_id=session.user_id, session_id=session.session_id
    )
    assert [message.message_id for message in history] == [
        first.message_id,
        second.message_id,
    ]
