"""Checkpoint retention purge that never touches chat history (FR-008)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from umbral.infrastructure.db.models.agent import AgentGraphRun
from umbral.infrastructure.db.models.chat import ChatMessage, ChatSession


class ThreadStore(Protocol):
    def delete_thread(self, thread_id: str) -> None: ...


class StaleSessionFinder(Protocol):
    def inactive_session_ids(self, before: datetime) -> tuple[UUID, ...]: ...


def purge_agent_checkpoints(
    *,
    finder: StaleSessionFinder,
    threads: ThreadStore,
    retention_days: int,
    now: datetime | None = None,
) -> int:
    """Delete checkpoint threads of sessions inactive beyond the window.

    Idempotent: sessions already purged simply have no thread to delete.
    History (chat_sessions/chat_messages) is never touched.
    """
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    session_ids = finder.inactive_session_ids(cutoff)
    for session_id in session_ids:
        threads.delete_thread(str(session_id))
    return len(session_ids)


class PostgresThreadStore:
    def __init__(self, saver: Any) -> None:
        self._saver = saver

    def delete_thread(self, thread_id: str) -> None:
        self._saver.delete_thread(thread_id)


class SqlAlchemyStaleSessionFinder:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def inactive_session_ids(self, before: datetime) -> tuple[UUID, ...]:
        message_active = exists(
            select(ChatMessage.id).where(
                ChatMessage.session_id == ChatSession.id,
                ChatMessage.created_at >= before,
            )
        )
        run_active = exists(
            select(AgentGraphRun.id).where(
                AgentGraphRun.session_id == ChatSession.id,
                AgentGraphRun.started_at >= before,
            )
        )
        with self.session_factory() as session:
            ids = session.scalars(
                select(ChatSession.id).where(~message_active, ~run_active)
            )
            return tuple(ids)
