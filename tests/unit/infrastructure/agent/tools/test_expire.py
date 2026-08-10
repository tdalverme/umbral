"""Proposal expiry maintenance duty tests (R-11, T023)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from umbral.infrastructure.agent.proposals.expire import (
    expire_search_profile_proposals,
)


class _Repo:
    def __init__(self) -> None:
        self.calls: list[datetime] = []
        self.count = 0

    def expire_pending(self, expired_before: datetime) -> int:
        self.calls.append(expired_before)
        return self.count


def test_expire_search_profile_proposals_returns_count() -> None:
    repo = _Repo()
    repo.count = 2
    now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)

    def session_factory() -> None:
        raise AssertionError("injected repository must be used")

    count = expire_search_profile_proposals(
        session_factory,  # type: ignore[arg-type]
        ttl_hours=24,
        now=now,
        repository=repo,  # type: ignore[arg-type]
    )
    assert count == 2
    assert len(repo.calls) == 1
    assert repo.calls[0] == now - timedelta(hours=24)
