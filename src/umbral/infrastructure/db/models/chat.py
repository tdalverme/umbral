"""Persistent chat sessions and immutable chat messages (H4.1)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base, IdentityAuditMixin

CHAT_SESSION_STATE = ENUM(
    "active", "paused", "archived", name="chat_session_state", create_type=True
)
CHAT_MESSAGE_ROLE = ENUM(
    "user", "assistant", "system", name="chat_message_role", create_type=True
)
CHAT_MESSAGE_STATE = ENUM("complete", name="chat_message_state", create_type=True)


class ChatSession(IdentityAuditMixin, Base):
    """A durable conversation tied to a user and a search profile."""

    __tablename__ = "chat_sessions"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        Index("ix_chat_sessions_user_status", "user_id", "status"),
        Index("ix_chat_sessions_profile", "search_profile_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("product_users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    search_profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(CHAT_SESSION_STATE, nullable=False)


class ChatMessage(IdentityAuditMixin, Base):
    """An immutable message with typed allowed content and run lineage."""

    __tablename__ = "chat_messages"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
        Index("ix_chat_messages_run", "graph_run_id"),
        Index(
            "uq_chat_messages_session_client",
            "session_id",
            "client_message_id",
            unique=True,
            postgresql_where=text("client_message_id IS NOT NULL"),
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(CHAT_MESSAGE_ROLE, nullable=False)
    content: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(CHAT_MESSAGE_STATE, nullable=False)
    graph_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_graph_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    client_message_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
