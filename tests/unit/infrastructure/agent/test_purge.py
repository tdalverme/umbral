"""Checkpoint retention purge unit tests (US3, FR-008/R-09)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from umbral.infrastructure.agent.purge import purge_agent_checkpoints

_NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


class _Finder:
    def __init__(self, ids: list[UUID]) -> None:
        self.ids = ids
        self.asked_cutoff: datetime | None = None

    def inactive_session_ids(self, before: datetime) -> tuple[UUID, ...]:
        self.asked_cutoff = before
        return tuple(self.ids)


class _Threads:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)


def test_purge_deletes_only_stale_threads_and_returns_count() -> None:
    stale = [uuid4(), uuid4()]
    finder = _Finder(stale)
    threads = _Threads()
    count = purge_agent_checkpoints(
        finder=finder,
        threads=threads,
        retention_days=30,
        now=_NOW,
    )
    assert count == 2
    assert sorted(threads.deleted) == sorted(str(uid) for uid in stale)
    assert finder.asked_cutoff == _NOW - timedelta(days=30)


def test_purge_is_idempotent_and_empty() -> None:
    finder = _Finder([])
    threads = _Threads()
    assert (
        purge_agent_checkpoints(finder=finder, threads=threads, retention_days=30) == 0
    )
    assert threads.deleted == []
