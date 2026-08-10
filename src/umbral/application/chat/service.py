"""Chat sessions and messages as durable product objects (UM-H4-001)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from umbral.application.chat.contracts import (
    ChatMessage,
    ChatMessageTooLong,
    ChatSession,
    ChatSessionNotActive,
    ChatSessionNotFound,
    ChatValidationError,
    SessionStatus,
    is_session_status,
    validate_message_content,
)
from umbral.application.chat.ports import (
    ChatMessageRepository,
    ChatSessionRepository,
    EventWriter,
    SearchProfileStatusReader,
)
from umbral.application.events.contracts import ProductEvent
from umbral.application.events.registry import EventsRegistrySpec, event_version

Clock = Callable[[], datetime]


class ChatService:
    """Owns chat session/message lifecycle and their product events."""

    def __init__(
        self,
        *,
        sessions: ChatSessionRepository,
        messages: ChatMessageRepository,
        profile_status: SearchProfileStatusReader,
        events_out: EventWriter,
        events_registry: EventsRegistrySpec,
        max_message_length: int = 4000,
        clock: Clock | None = None,
    ) -> None:
        self.sessions = sessions
        self.messages = messages
        self.profile_status = profile_status
        self.events_out = events_out
        self.events_registry = events_registry
        self.max_message_length = max_message_length
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def create_session(
        self,
        *,
        user_id: UUID,
        search_profile_id: UUID,
        correlation_id: UUID,
        now: datetime | None = None,
    ) -> ChatSession:
        status = self._profile_status(search_profile_id)
        session = ChatSession(
            session_id=uuid4(),
            user_id=user_id,
            search_profile_id=search_profile_id,
            status=status,
            created_at=now or self.clock(),
            correlation_id=correlation_id,
        )
        self.sessions.create(session)
        self._emit_server_event(
            event_type="chat.session_created.v1",
            correlation_id=correlation_id,
            actor_id=user_id,
            payload={
                "session_id": str(session.session_id),
                "search_profile_id": str(search_profile_id),
            },
        )
        return session

    def get_session(self, *, user_id: UUID, session_id: UUID) -> ChatSession:
        session = self.sessions.get_by_id(user_id=user_id, session_id=session_id)
        if session is None:
            raise ChatSessionNotFound()
        return session

    def list_history(
        self, *, user_id: UUID, session_id: UUID
    ) -> tuple[ChatMessage, ...]:
        session = self.get_session(user_id=user_id, session_id=session_id)
        return self.messages.list_by_session(session.session_id)

    def list_sessions(
        self, *, user_id: UUID, search_profile_id: UUID
    ) -> tuple[ChatSession, ...]:
        """Sessions of a radar, newest first (the panel resumes the latest)."""
        return self.sessions.list_by_profile(user_id, search_profile_id)

    def assert_accepts_turn(self, *, user_id: UUID, session_id: UUID) -> ChatSession:
        session = self.get_session(user_id=user_id, session_id=session_id)
        if session.status != "active":
            raise ChatSessionNotActive()
        return session

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
        session = self.assert_accepts_turn(user_id=user_id, session_id=session_id)
        content: dict[str, object] = {"kind": "text", "text": text}
        if context is not None:
            content["context"] = dict(context)
        self._validate_content(content)
        if client_message_id is not None:
            replay = self.messages.find_by_client_message_id(
                session.session_id, client_message_id
            )
            if replay is not None:
                # Idempotent send (R-06): replay with the same key returns the
                # recorded message; 0 duplicates and 0 new runs (FR-024).
                return replay
        message = ChatMessage(
            message_id=uuid4(),
            session_id=session.session_id,
            role="user",
            content=content,
            graph_run_id=None,
            created_at=now or self.clock(),
            correlation_id=correlation_id,
            client_message_id=client_message_id,
        )
        self.messages.append(message)
        self._emit_server_event(
            event_type="chat.message_created.v1",
            correlation_id=correlation_id,
            actor_id=user_id,
            payload={
                "session_id": str(session.session_id),
                "message_id": str(message.message_id),
                "role": message.role,
            },
        )
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
        session = self.get_session(user_id=user_id, session_id=session_id)
        content: dict[str, object] = {
            "kind": "reply",
            "text": text,
            "refs": [dict(ref) for ref in refs],
        }
        self._validate_content(content)
        message = ChatMessage(
            message_id=uuid4(),
            session_id=session.session_id,
            role="assistant",
            content=content,
            graph_run_id=graph_run_id,
            created_at=now or self.clock(),
            correlation_id=correlation_id,
        )
        self.messages.append(message)
        self._emit_server_event(
            event_type="chat.message_created.v1",
            correlation_id=correlation_id,
            actor_id=user_id,
            payload={
                "session_id": str(session.session_id),
                "message_id": str(message.message_id),
                "role": message.role,
            },
        )
        return message

    def _profile_status(self, search_profile_id: UUID) -> SessionStatus:
        status = self.profile_status.status(search_profile_id)
        if not is_session_status(status):
            raise ChatValidationError(("chat.profile_status_invalid",))
        return cast(SessionStatus, status)

    def _validate_content(self, content: Mapping[str, object]) -> None:
        errors = validate_message_content(
            content, max_text_length=self.max_message_length
        )
        if "chat.message_too_long" in errors:
            raise ChatMessageTooLong()
        if errors:
            raise ChatValidationError(errors)

    def _emit_server_event(
        self,
        *,
        event_type: str,
        correlation_id: UUID,
        actor_id: UUID | None,
        payload: Mapping[str, object],
    ) -> None:
        version = event_version(self.events_registry, event_type)
        event = ProductEvent(
            event_id=uuid4(),
            event_type=event_type,
            event_version=version or 1,
            actor_id=actor_id,
            occurred_at=self.clock(),
            correlation_id=correlation_id,
            payload=dict(payload),
        )
        self.events_out.insert(event)
