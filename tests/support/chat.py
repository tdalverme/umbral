"""In-memory chat fakes for unit tests."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import UUID

from umbral.application.chat.contracts import ChatMessage, ChatSession
from umbral.application.events.contracts import ProductEvent

_NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


class InMemoryChatSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[UUID, ChatSession] = {}

    def create(self, session: ChatSession) -> ChatSession:
        self.sessions[session.session_id] = session
        return session

    def get_by_id(self, user_id: UUID, session_id: UUID) -> ChatSession | None:
        session = self.sessions.get(session_id)
        if session is None or session.user_id != user_id:
            return None
        return session

    def bind_profile(
        self, session_id: UUID, search_profile_id: UUID
    ) -> ChatSession | None:
        session = self.sessions.get(session_id)
        if session is None:
            return None
        updated = ChatSession(
            session_id=session.session_id,
            user_id=session.user_id,
            search_profile_id=search_profile_id,
            status=session.status,
            created_at=session.created_at,
            correlation_id=session.correlation_id,
        )
        self.sessions[session_id] = updated
        return updated

    def list_by_user(self, user_id: UUID) -> tuple[ChatSession, ...]:
        return tuple(
            session for session in self.sessions.values() if session.user_id == user_id
        )

    def list_by_profile(
        self, user_id: UUID, search_profile_id: UUID
    ) -> tuple[ChatSession, ...]:
        sessions = [
            session
            for session in self.sessions.values()
            if session.user_id == user_id
            and session.search_profile_id == search_profile_id
        ]
        return tuple(reversed(sessions))


class InMemoryChatMessageRepository:
    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []

    def append(self, message: ChatMessage) -> ChatMessage:
        self.messages.append(message)
        return message

    def list_by_session(self, session_id: UUID) -> tuple[ChatMessage, ...]:
        return tuple(
            message for message in self.messages if message.session_id == session_id
        )

    def find_by_client_message_id(
        self, session_id: UUID, client_message_id: UUID
    ) -> ChatMessage | None:
        for message in self.messages:
            if (
                message.session_id == session_id
                and message.client_message_id == client_message_id
            ):
                return message
        return None


class FixedProfileStatusReader:
    def __init__(self, statuses: dict[UUID, str] | None = None) -> None:
        self.statuses = statuses or {}

    def status(self, search_profile_id: UUID) -> str:
        return self.statuses.get(search_profile_id, "active")


class RecordingEventWriter:
    def __init__(self) -> None:
        self.events: list[ProductEvent] = []

    def insert(self, event: ProductEvent) -> None:
        self.events.append(event)


class RecordingConversation:
    """Records calls and returns fixed sessions/messages for the agent graph."""

    def __init__(self) -> None:
        self.user_messages: list[ChatMessage] = []
        self.assistant_messages: list[ChatMessage] = []
        self.accept_calls = 0

    def assert_accepts_turn(self, *, user_id: UUID, session_id: UUID) -> ChatSession:
        self.accept_calls += 1
        return ChatSession(
            session_id=session_id,
            user_id=user_id,
            search_profile_id=UUID(int=0),
            status="active",
            created_at=_NOW,
            correlation_id=UUID(int=0),
        )

    def append_user_message(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        text: str,
        correlation_id: UUID,
        now: datetime | None = None,
        client_message_id: UUID | None = None,
        context: Mapping[str, object] | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            message_id=UUID(int=len(self.user_messages) + 1),
            session_id=session_id,
            role="user",
            content={"kind": "text", "text": text},
            created_at=now or _NOW,
            correlation_id=correlation_id,
            client_message_id=client_message_id,
        )
        self.user_messages.append(message)
        return message

    def persist_assistant_message(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        text: str,
        refs: tuple[Mapping[str, str], ...],
        graph_run_id: UUID,
        correlation_id: UUID,
        now: datetime | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            message_id=UUID(int=100 + len(self.assistant_messages)),
            session_id=session_id,
            role="assistant",
            content={"kind": "reply", "text": text, "refs": [dict(r) for r in refs]},
            graph_run_id=graph_run_id,
            created_at=now or _NOW,
            correlation_id=correlation_id,
        )
        self.assistant_messages.append(message)
        return message
