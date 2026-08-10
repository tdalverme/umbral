"""SQLAlchemy repositories for the chat domain (H4.1)."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from umbral.application.chat.contracts import (
    ChatMessage,
    ChatSession,
    MessageRole,
    SessionStatus,
)
from umbral.infrastructure.db.models.chat import (
    ChatMessage as ChatMessageModel,
)
from umbral.infrastructure.db.models.chat import ChatSession as ChatSessionModel
from umbral.infrastructure.db.models.radar import SearchProfile

SessionFactory = Callable[[], Session]


class SqlAlchemyChatSessionRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def create(self, session: ChatSession) -> ChatSession:
        with self.session_factory() as current:
            current.add(
                ChatSessionModel(
                    id=session.session_id,
                    created_at=session.created_at,
                    updated_at=session.created_at,
                    actor_kind="service",
                    actor_id=str(session.user_id),
                    source="chat.session",
                    correlation_id=session.correlation_id,
                    user_id=session.user_id,
                    search_profile_id=session.search_profile_id,
                    status=session.status,
                )
            )
            current.commit()
        return session

    def get_by_id(self, user_id: UUID, session_id: UUID) -> ChatSession | None:
        with self.session_factory() as current:
            model = current.scalar(
                select(ChatSessionModel).where(
                    ChatSessionModel.id == session_id,
                    ChatSessionModel.user_id == user_id,
                )
            )
            return _to_session(model) if model is not None else None

    def list_by_user(self, user_id: UUID) -> tuple[ChatSession, ...]:
        with self.session_factory() as current:
            models = current.scalars(
                select(ChatSessionModel)
                .where(ChatSessionModel.user_id == user_id)
                .order_by(ChatSessionModel.created_at.desc())
            )
            return tuple(_to_session(model) for model in models)

    def list_by_profile(
        self, user_id: UUID, search_profile_id: UUID
    ) -> tuple[ChatSession, ...]:
        with self.session_factory() as current:
            models = current.scalars(
                select(ChatSessionModel)
                .where(
                    ChatSessionModel.user_id == user_id,
                    ChatSessionModel.search_profile_id == search_profile_id,
                )
                .order_by(ChatSessionModel.created_at.desc())
            )
            return tuple(_to_session(model) for model in models)


class SqlAlchemyChatMessageRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def append(self, message: ChatMessage) -> ChatMessage:
        with self.session_factory() as current:
            current.add(
                ChatMessageModel(
                    id=message.message_id,
                    created_at=message.created_at,
                    updated_at=message.created_at,
                    actor_kind="service",
                    actor_id=None,
                    source="chat.message",
                    correlation_id=message.correlation_id,
                    session_id=message.session_id,
                    role=message.role,
                    content=dict(message.content),
                    state=message.state,
                    graph_run_id=message.graph_run_id,
                    client_message_id=message.client_message_id,
                )
            )
            current.commit()
        return message

    def list_by_session(self, session_id: UUID) -> tuple[ChatMessage, ...]:
        with self.session_factory() as current:
            models = current.scalars(
                select(ChatMessageModel)
                .where(ChatMessageModel.session_id == session_id)
                .order_by(ChatMessageModel.created_at, ChatMessageModel.id)
            )
            return tuple(_to_message(model) for model in models)

    def find_by_client_message_id(
        self, session_id: UUID, client_message_id: UUID
    ) -> ChatMessage | None:
        with self.session_factory() as current:
            model = current.scalar(
                select(ChatMessageModel).where(
                    ChatMessageModel.session_id == session_id,
                    ChatMessageModel.client_message_id == client_message_id,
                )
            )
            return _to_message(model) if model is not None else None


class SqlAlchemySearchProfileStatusReader:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def status(self, search_profile_id: UUID) -> str:
        with self.session_factory() as current:
            status = current.scalar(
                select(SearchProfile.status).where(
                    SearchProfile.id == search_profile_id
                )
            )
        if status is None:
            raise LookupError(f"search profile not found: {search_profile_id}")
        return status


def _to_session(model: ChatSessionModel) -> ChatSession:
    return ChatSession(
        session_id=model.id,
        user_id=model.user_id,
        search_profile_id=model.search_profile_id,
        status=cast(SessionStatus, model.status),
        created_at=model.created_at,
        correlation_id=model.correlation_id,
    )


def _to_message(model: ChatMessageModel) -> ChatMessage:
    return ChatMessage(
        message_id=model.id,
        session_id=model.session_id,
        role=cast(MessageRole, model.role),
        content=dict(model.content or {}),
        state=model.state,
        graph_run_id=model.graph_run_id,
        created_at=model.created_at,
        correlation_id=model.correlation_id,
        client_message_id=model.client_message_id,
    )
