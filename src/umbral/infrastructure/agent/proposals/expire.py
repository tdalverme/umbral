"""Expiry maintenance duty for search-profile update proposals (R-11)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from umbral.application.agent.tools.ports import ProposalRepository
from umbral.infrastructure.db.repositories.agent import (
    SessionFactory,
    SqlAlchemyProposalRepository,
)

Clock = Callable[[], datetime]


def expire_search_profile_proposals(
    session_factory: SessionFactory,
    *,
    ttl_hours: int = 24,
    now: datetime | None = None,
    repository: ProposalRepository | None = None,
) -> int:
    """Mark pending proposals past ``AGENT_PROPOSAL_TTL_HOURS`` as rejected.

    Deterministic, idempotent (running twice is a no-op) and never touches
    the search profile (clarification Q2, FR-009).
    """

    current = now or datetime.now(timezone.utc)
    repo = repository or SqlAlchemyProposalRepository(session_factory)
    return repo.expire_pending(current - timedelta(hours=ttl_hours))
