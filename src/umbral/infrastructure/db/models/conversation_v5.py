"""Durable V5 conversation command receipts (idempotency guard)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, String
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base

CONVERSATION_V5_RECEIPT_STATE = ENUM(
    "started",
    "applied",
    "failed",
    name="conversation_v5_receipt_state",
    create_type=True,
)


class ConversationV5CommandReceipt(Base):
    """One idempotent command execution guard, keyed by idempotency key."""

    __tablename__ = "conversation_v5_command_receipts"
    __table_args__ = (
        Index(
            "ix_conversation_v5_receipts_session",
            "session_id",
            "created_at",
        ),
    )

    idempotency_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    message_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    act_id: Mapped[str] = mapped_column(String(64), nullable=False)
    command_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(
        CONVERSATION_V5_RECEIPT_STATE, nullable=False
    )
    result: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    correlation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
