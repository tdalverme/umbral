# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Proposal repository lifecycle over Postgres (FR-008, R-03/R-05)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from tests.integration.agent.conftest import seed_profile, seed_user
from tests.integration.chat.conftest import build_chat

from umbral.application.agent.tools.contracts import Proposal
from umbral.infrastructure.db.repositories.agent import SqlAlchemyProposalRepository

_NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def _session(factory, user_id, profile):
    chat = build_chat(factory)
    return chat.create_session(
        user_id=user_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )


def test_proposal_repo_insert_approve_and_expire(agent_backend) -> None:
    factory, _url = agent_backend
    user_id = seed_user(factory)
    profile = seed_profile(factory, user_id)
    session = _session(factory, user_id, profile)
    repo = SqlAlchemyProposalRepository(factory)

    proposal = Proposal(
        proposal_id=uuid4(),
        session_id=session.session_id,
        search_profile_id=profile.profile_id,
        base_profile_version=profile.version,
        diff={"budget_max": 200000},
        impact={"fields_changed": ["budget_max"], "will_recompute": True},
        state="pending",
        expires_at=_NOW + timedelta(hours=24),
        correlation_id=uuid4(),
    )
    repo.insert(proposal)

    stored = repo.get(proposal.proposal_id, session.session_id, user_id)
    assert stored is not None
    assert stored.state == "pending"
    assert stored.base_profile_version == profile.version

    approved = repo.mark_approved(
        proposal.proposal_id, "k-1", profile_version=profile.version + 1
    )
    assert approved is not None
    assert approved.state == "approved"
    assert approved.applied_idempotency_key == "k-1"

    replay = repo.get(proposal.proposal_id, session.session_id, user_id)
    assert replay is not None and replay.applied_profile_version == profile.version + 1

    expired = repo.expire_pending(_NOW - timedelta(hours=1))
    assert expired == 0  # already approved


def test_proposal_repo_expire_marks_pending_as_rejected(agent_backend) -> None:
    factory, _url = agent_backend
    user_id = seed_user(factory)
    profile = seed_profile(factory, user_id)
    session = _session(factory, user_id, profile)
    repo = SqlAlchemyProposalRepository(factory)

    proposal = Proposal(
        proposal_id=uuid4(),
        session_id=session.session_id,
        search_profile_id=profile.profile_id,
        base_profile_version=profile.version,
        diff={"budget_max": 200000},
        impact={},
        state="pending",
        expires_at=_NOW - timedelta(hours=2),
        correlation_id=uuid4(),
    )
    repo.insert(proposal)
    count = repo.expire_pending(_NOW)
    assert count == 1

    stored = repo.get(proposal.proposal_id, session.session_id, user_id)
    assert stored is not None
    assert stored.state == "rejected"
    assert stored.rejection_reason == "expired"
