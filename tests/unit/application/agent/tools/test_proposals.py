# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Proposal service lifecycle tests (FR-007..FR-012, T020)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from umbral.application.agent.tools.contracts import (
    Proposal,
    ProposalExpired,
    ProposalInvalidChange,
    ProposalNotFound,
    ProposalNotPending,
    ProposalStale,
)
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.events.contracts import ProductEvent
from umbral.application.events.registry import parse_events_registry
from umbral.application.radar.contracts import SearchProfile

USER_ID = UUID(int=1)
SESSION_ID = UUID(int=2)
PROFILE_ID = UUID(int=5)
CORRELATION_ID = UUID(int=9)
NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


def _registry():
    import json
    from pathlib import Path

    data = json.loads(
        Path("contracts/events/v1/events-registry.json").read_text(encoding="utf-8")
    )
    return parse_events_registry(data)


class _ProposalRepo:
    def __init__(self) -> None:
        self.proposals: dict[UUID, Proposal] = {}

    def insert(self, proposal: Proposal) -> Proposal:
        self.proposals[proposal.proposal_id] = proposal
        return proposal

    def get(self, proposal_id, session_id, user_id) -> Proposal | None:
        return self.proposals.get(proposal_id)

    def latest_pending_for_profile(self, search_profile_id, session_id):
        return None

    def mark_approved(self, proposal_id, key, *, profile_version=None, run_id=None):
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            return None
        updated = replace(
            proposal,
            state="approved",
            applied_idempotency_key=key,
            applied_profile_version=profile_version,
            applied_run_id=run_id,
        )
        self.proposals[proposal_id] = updated
        return updated

    def mark_rejected(self, proposal_id, reason, rejection_at):
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            return None
        updated = replace(proposal, state="rejected", rejection_reason=reason)
        self.proposals[proposal_id] = updated
        return updated

    def expire_pending(self, expired_before) -> int:
        return 0


class _Radar:
    def __init__(self, profile: SearchProfile) -> None:
        self.profile = profile
        self.applied: list[dict[str, object]] = []
        self.fail_next_concurrency = False

    def validate_change(self, *, owner_id, profile_id, changes):
        return self.profile

    def update_profile(
        self,
        *,
        owner_id,
        profile_id,
        expected_version,
        changes,
        correlation_id,
        actor_kind="service",
        actor_id=None,
    ):
        if self.fail_next_concurrency:
            from umbral.domain.errors import ConcurrencyConflict

            raise ConcurrencyConflict(expected_version=3, actual_version=4)
        self.applied.append(
            {"expected_version": expected_version, "changes": dict(changes)}
        )
        current = self.profile
        updated = SearchProfile(
            profile_id=current.profile_id,
            owner_id=current.owner_id,
            name=current.name,
            operation=current.operation,
            zones=current.zones,
            budget_max=current.budget_max,
            budget_min=current.budget_min,
            min_rooms=current.min_rooms,
            surface_min=current.surface_min,
            surface_max=current.surface_max,
            status=current.status,
            unknown_strategy=current.unknown_strategy,
            version=current.version + 1,
            current_version_id=current.current_version_id,
            latest_run_id=current.latest_run_id,
            created_at=current.created_at,
            updated_at=NOW,
            correlation_id=current.correlation_id,
            actor_kind=current.actor_kind,
            actor_id=current.actor_id,
        )
        return updated, None


class _Events:
    def __init__(self) -> None:
        self.events: list[ProductEvent] = []

    def insert(self, event: ProductEvent) -> None:
        self.events.append(event)


def _make_service(
    **kwargs,
) -> tuple[SearchProfileUpdateProposals, _ProposalRepo, _Radar, _Events]:
    repo = _ProposalRepo()
    radar = _Radar(_profile())
    events = _Events()
    service = SearchProfileUpdateProposals(
        repository=repo,
        radar=radar,
        events=events,
        events_registry=_registry(),
        ttl_hours=24,
        clock=lambda: NOW,
    )
    return service, repo, radar, events


def _profile() -> SearchProfile:
    return SearchProfile(
        profile_id=PROFILE_ID,
        owner_id=USER_ID,
        name="radar",
        operation="rental",
        zones=("palermo",),
        budget_max=150000,
        budget_min=None,
        min_rooms=2,
        surface_min=None,
        surface_max=None,
        status="active",
        unknown_strategy={},
        version=3,
        current_version_id=None,
        latest_run_id=None,
        created_at=NOW,
        updated_at=NOW,
        correlation_id=CORRELATION_ID,
        actor_kind="service",
        actor_id=None,
    )


def _base_args(proposal_id, *, confirmation=True, key="k-1"):
    return dict(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        proposal_id=proposal_id,
        confirmation=confirmation,
        idempotency_key=key,
        correlation_id=CORRELATION_ID,
    )


def test_propose_creates_pending_durable_proposal_with_base_version() -> None:
    service, repo, _, events = _make_service()
    proposal = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"budget_max": 200000},
        correlation_id=CORRELATION_ID,
    )
    assert proposal.state == "pending"
    assert proposal.base_profile_version == 3
    assert proposal.diff == {"budget_max": 200000}
    assert proposal.impact["will_recompute"] is True
    assert proposal.expires_at == NOW + timedelta(hours=24)
    assert repo.proposals[proposal.proposal_id] is proposal
    assert any(
        e.event_type == "search_profile.update_proposed.v1" for e in events.events
    )


def test_propose_rejects_unknown_change_fields() -> None:
    service, _, _, _ = _make_service()
    with pytest.raises(ProposalInvalidChange):
        service.propose(
            user_id=USER_ID,
            session_id=SESSION_ID,
            search_profile_id=PROFILE_ID,
            change={"budget_max": 200000, "status": "paused"},
            correlation_id=CORRELATION_ID,
        )


def test_apply_requires_confirmation() -> None:
    service, _, _, _ = _make_service()
    proposal = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"budget_max": 200000},
        correlation_id=CORRELATION_ID,
    )
    from umbral.application.agent.tools.contracts import ProposalNotConfirmed

    with pytest.raises(ProposalNotConfirmed):
        service.apply(**_base_args(proposal.proposal_id, confirmation=False))


def test_apply_versions_profile_and_emits_event() -> None:
    service, _, radar, events = _make_service()
    proposal = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"budget_max": 200000},
        correlation_id=CORRELATION_ID,
    )
    result = service.apply(**_base_args(proposal.proposal_id))
    assert result.state == "approved"
    assert result.profile_version == 4
    assert radar.applied[0]["expected_version"] == 3
    assert any(
        e.event_type == "search_profile.update_applied.v1" for e in events.events
    )


def test_apply_replay_with_same_key_returns_recorded_result() -> None:
    service, _, radar, _ = _make_service()
    proposal = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"budget_max": 200000},
        correlation_id=CORRELATION_ID,
    )
    first = service.apply(**_base_args(proposal.proposal_id))
    assert first.state == "approved"
    replay = service.apply(**_base_args(proposal.proposal_id))
    assert replay.state == "approved"
    assert replay.profile_version == first.profile_version
    assert len(radar.applied) == 1


def test_apply_rejects_used_proposal_with_different_key() -> None:
    service, _, radar, _ = _make_service()
    proposal = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"budget_max": 200000},
        correlation_id=CORRELATION_ID,
    )
    service.apply(**_base_args(proposal.proposal_id, key="k-1"))
    with pytest.raises(ProposalNotPending):
        service.apply(**_base_args(proposal.proposal_id, key="k-2"))
    assert len(radar.applied) == 1


def test_apply_obsolescence_marks_rejected() -> None:
    service, _, radar, _ = _make_service()
    proposal = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"budget_max": 200000},
        correlation_id=CORRELATION_ID,
    )
    radar.fail_next_concurrency = True
    with pytest.raises(ProposalStale):
        service.apply(**_base_args(proposal.proposal_id))
    stored = service.repository.get(proposal.proposal_id, SESSION_ID, USER_ID)
    assert stored is not None and stored.state == "rejected"


def test_apply_rejects_expired_proposal() -> None:
    service, repo, _, _ = _make_service()
    proposal = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"budget_max": 200000},
        correlation_id=CORRELATION_ID,
    )
    expired = Proposal(
        proposal_id=proposal.proposal_id,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        base_profile_version=3,
        diff={"budget_max": 200000},
        impact={},
        state="pending",
        expires_at=NOW - timedelta(hours=1),
        correlation_id=CORRELATION_ID,
    )
    repo.proposals[proposal.proposal_id] = expired
    with pytest.raises(ProposalExpired):
        service.apply(**_base_args(proposal.proposal_id))
    assert repo.proposals[proposal.proposal_id].state == "rejected"


def test_apply_scope_denied_for_other_profile() -> None:
    service, _, _, _ = _make_service()
    proposal = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"budget_max": 200000},
        correlation_id=CORRELATION_ID,
    )
    args = _base_args(proposal.proposal_id)
    args["search_profile_id"] = UUID(int=999)
    with pytest.raises(ProposalNotFound):
        service.apply(**args)

