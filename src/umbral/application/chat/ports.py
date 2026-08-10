"""Ports for the persistent chat domain (H4.1)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol
from uuid import UUID

from umbral.application.chat.contracts import ChatMessage, ChatSession
from umbral.application.events.contracts import ProductEvent


class ChatSessionRepository(Protocol):
    def create(self, session: ChatSession) -> ChatSession: ...

    def get_by_id(self, user_id: UUID, session_id: UUID) -> ChatSession | None: ...

    def list_by_user(self, user_id: UUID) -> tuple[ChatSession, ...]: ...

    def list_by_profile(
        self, user_id: UUID, search_profile_id: UUID
    ) -> tuple[ChatSession, ...]: ...


class ChatMessageRepository(Protocol):
    def append(self, message: ChatMessage) -> ChatMessage: ...

    def list_by_session(self, session_id: UUID) -> tuple[ChatMessage, ...]: ...

    def find_by_client_message_id(
        self, session_id: UUID, client_message_id: UUID
    ) -> ChatMessage | None: ...


class SearchProfileStatusReader(Protocol):
    def status(self, search_profile_id: UUID) -> str: ...


class EventWriter(Protocol):
    def insert(self, event: ProductEvent) -> None: ...


class ConversationGateway(Protocol):
    """Application seam consumed by the agent runtime."""

    def assert_accepts_turn(
        self, *, user_id: UUID, session_id: UUID
    ) -> ChatSession: ...

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
    ) -> ChatMessage: ...

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
    ) -> ChatMessage: ...
