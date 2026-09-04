"""PostgreSQL races for the durable V5 proposal queue."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from tests.integration.agent.conftest import seed_profile, seed_user
from tests.integration.chat.conftest import build_chat

from umbral.application.agent.tools.contracts import Proposal
from umbral.infrastructure.db.repositories.agent import SqlAlchemyProposalRepository

_NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def _proposal(session, profile, *, diff: dict[str, object], act_id: str) -> Proposal:
    return Proposal(
        proposal_id=uuid4(),
        session_id=session.session_id,
        search_profile_id=profile.profile_id,
        base_profile_version=profile.version,
        diff=diff,
        impact={},
        state="pending",
        expires_at=_NOW + timedelta(hours=1),
        source_act_id=act_id,
    )


def test_concurrent_enqueue_assigns_unique_order_and_shared_total(
    agent_backend,
) -> None:
    factory, _url = agent_backend
    user_id = seed_user(factory)
    profile = seed_profile(factory, user_id)
    session = build_chat(factory).create_session(
        user_id=user_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    repo = SqlAlchemyProposalRepository(factory)
    proposals = [
        _proposal(session, profile, diff={"budget_max": 900}, act_id="a1"),
        _proposal(session, profile, diff={"budget_max": 1000}, act_id="a2"),
    ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        stored = list(pool.map(repo.enqueue_pending, proposals))

    assert sorted(
        (item.queue_ordinal, item.queue_total) for item in stored
    ) == [(1, 1), (2, 2)]
    durable = repo.pending_for_profile(profile.profile_id, session.session_id)
    assert [item.queue_ordinal for item in durable] == [1, 2]
    assert {item.queue_total for item in durable} == {2}


def test_correction_and_resolution_are_serialized(agent_backend) -> None:
    factory, _url = agent_backend
    user_id = seed_user(factory)
    profile = seed_profile(factory, user_id)
    session = build_chat(factory).create_session(
        user_id=user_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    repo = SqlAlchemyProposalRepository(factory)
    original = repo.enqueue_pending(
        _proposal(session, profile, diff={"zones": ["palermo"]}, act_id="palermo")
    )
    successor = _proposal(
        session, profile, diff={"zones": ["belgrano"]}, act_id="belgrano"
    )

    def correct():
        return repo.supersede_and_insert(original.proposal_id, successor)

    def resolve():
        return repo.apply_pending(
            original.proposal_id,
            "decision-1",
            lambda current: (current.base_profile_version + 1, None),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        corrected, resolved = pool.map(lambda fn: fn(), (correct, resolve))

    stored_original = repo.get(original.proposal_id, session.session_id, user_id)
    assert stored_original is not None
    assert not (
        corrected is not None
        and corrected.state == "pending"
        and resolved is not None
        and resolved.state == "approved"
    )
    if corrected is None:
        assert stored_original.state == "approved"
        assert resolved is not None and resolved.state == "approved"
    else:
        assert stored_original.state == "rejected"
        assert stored_original.superseded_by_proposal_id == successor.proposal_id
        assert resolved is not None and resolved.state == "rejected"
        successor_stored = repo.get(successor.proposal_id, session.session_id, user_id)
        assert successor_stored is not None and successor_stored.state == "pending"


def test_correction_and_rejection_are_serialized(agent_backend) -> None:
    factory, _url = agent_backend
    user_id = seed_user(factory)
    profile = seed_profile(factory, user_id)
    session = build_chat(factory).create_session(
        user_id=user_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    repo = SqlAlchemyProposalRepository(factory)
    original = repo.enqueue_pending(
        _proposal(session, profile, diff={"zones": ["palermo"]}, act_id="palermo")
    )
    successor = _proposal(
        session, profile, diff={"zones": ["belgrano"]}, act_id="belgrano"
    )

    def correct():
        return repo.supersede_and_insert(original.proposal_id, successor)

    def reject():
        return repo.reject_pending(
            original.proposal_id, "user", _NOW, rejection_note="no longer wanted"
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        corrected, rejected = pool.map(lambda fn: fn(), (correct, reject))

    stored_original = repo.get(original.proposal_id, session.session_id, user_id)
    assert stored_original is not None
    assert stored_original.state == "rejected"
    if corrected is None:
        assert stored_original.rejection_reason == "user"
        assert rejected is not None and rejected.state == "rejected"
    else:
        assert stored_original.rejection_reason == "edited"
        assert stored_original.superseded_by_proposal_id == successor.proposal_id
        assert rejected is not None and rejected.state == "rejected"
        successor_stored = repo.get(successor.proposal_id, session.session_id, user_id)
        assert successor_stored is not None and successor_stored.state == "pending"
