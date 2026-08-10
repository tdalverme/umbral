"""Chat persistence integration tests (US1, SC-001)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session
from tests.integration.chat.conftest import build_chat, seed_profile, seed_user

from umbral.application.chat.contracts import ChatMessageTooLong
from umbral.infrastructure.db.models.chat import ChatMessage as ChatMessageModel
from umbral.infrastructure.db.models.radar import SearchProfile

SessionFactory = Callable[[], Session]
_NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def test_session_is_created_and_owner_scoped(chat_backend: SessionFactory) -> None:
    chat = build_chat(chat_backend)
    owner_id = seed_user(chat_backend)
    profile = seed_profile(chat_backend, owner_id)
    session = chat.create_session(
        user_id=owner_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    assert chat.get_session(user_id=owner_id, session_id=session.session_id) is not None
    other_user = seed_user(chat_backend)
    with pytest.raises(Exception):
        chat.get_session(user_id=other_user, session_id=session.session_id)


def test_ordered_history(chat_backend: SessionFactory) -> None:
    chat = build_chat(chat_backend)
    owner_id = seed_user(chat_backend)
    profile = seed_profile(chat_backend, owner_id)
    session = chat.create_session(
        user_id=owner_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    first = chat.append_user_message(
        user_id=owner_id,
        session_id=session.session_id,
        text="primero",
        correlation_id=uuid4(),
        now=_NOW,
    )
    second = chat.append_user_message(
        user_id=owner_id,
        session_id=session.session_id,
        text="segundo",
        correlation_id=uuid4(),
        now=_NOW + timedelta(seconds=1),
    )
    history = chat.list_history(user_id=owner_id, session_id=session.session_id)
    assert [message.message_id for message in history] == [
        first.message_id,
        second.message_id,
    ]
    assert all(message.state == "complete" for message in history)


def test_messages_are_persisted_in_the_database(chat_backend: SessionFactory) -> None:
    chat = build_chat(chat_backend)
    owner_id = seed_user(chat_backend)
    profile = seed_profile(chat_backend, owner_id)
    session = chat.create_session(
        user_id=owner_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    message = chat.append_user_message(
        user_id=owner_id,
        session_id=session.session_id,
        text="inmutable",
        correlation_id=uuid4(),
    )
    with chat_backend() as current:
        row = current.get(ChatMessageModel, message.message_id)
        assert row is not None
        assert row.content == {"kind": "text", "text": "inmutable"}


def test_length_limit_is_enforced(chat_backend: SessionFactory) -> None:
    chat = build_chat(chat_backend)
    owner_id = seed_user(chat_backend)
    profile = seed_profile(chat_backend, owner_id)
    session = chat.create_session(
        user_id=owner_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    with pytest.raises(ChatMessageTooLong):
        chat.append_user_message(
            user_id=owner_id,
            session_id=session.session_id,
            text="x" * 5000,
            correlation_id=uuid4(),
        )


def test_status_mirrors_search_profile(chat_backend: SessionFactory) -> None:
    chat = build_chat(chat_backend)
    owner_id = seed_user(chat_backend)
    profile = seed_profile(chat_backend, owner_id)
    with chat_backend() as current:
        current.execute(
            update(SearchProfile)
            .where(SearchProfile.id == profile.profile_id)
            .values(status="paused")
        )
        current.commit()
    session = chat.create_session(
        user_id=owner_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    assert session.status == "paused"
