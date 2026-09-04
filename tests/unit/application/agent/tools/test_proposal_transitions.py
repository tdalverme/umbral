# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Interactive proposal transitions: reject and derived edit (R-05, T023)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from umbral.application.agent.tools.contracts import (
    Proposal,
    ProposalNotPending,
)
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.radar.contracts import SearchProfile
from umbral.infrastructure.radar.contract_loader import load_events_registry

USER_ID = UUID(int=1)
SESSION_ID = UUID(int=2)
PROFILE_ID = UUID(int=5)
CORRELATION_ID = UUID(int=20)
NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


class _Events:
    def __init__(self) -> None:
        self.events: list[object] = []

    def insert(self, event: object) -> None:
        self.events.append(event)


class _Repo:
    def __init__(self) -> None:
        self.proposals: dict[UUID, Proposal] = {}

    def insert(self, proposal: Proposal) -> Proposal:
        self.proposals[proposal.proposal_id] = proposal
        return proposal

    def enqueue_pending(self, proposal: Proposal) -> Proposal:
        ordinal = max(
            (p.queue_ordinal for p in self.proposals.values()
             if p.search_profile_id == proposal.search_profile_id
             and p.session_id == proposal.session_id and p.state == "pending"),
            default=0,
        ) + 1
        queued = replace(proposal, queue_ordinal=ordinal, queue_total=ordinal)
        self.proposals[queued.proposal_id] = queued
        return queued

    def supersede_and_insert(self, proposal_id, successor):
        original = self.proposals.get(proposal_id)
        if original is None or original.state != "pending":
            return None
        self.proposals[proposal_id] = replace(
            original, state="rejected", rejection_reason="edited",
            superseded_by_proposal_id=successor.proposal_id,
        )
        self.proposals[successor.proposal_id] = successor
        return successor

    def apply_pending(self, proposal_id, key, operation):
        proposal = self.proposals.get(proposal_id)
        if proposal is None or proposal.state != "pending":
            return proposal
        version, run_id = operation(proposal)
        updated = replace(
            proposal, state="approved", applied_idempotency_key=key,
            applied_profile_version=version, applied_run_id=run_id,
        )
        self.proposals[proposal_id] = updated
        return updated

    def get(self, proposal_id, session_id, user_id):
        return self.proposals.get(proposal_id)

    def latest_pending_for_profile(self, search_profile_id, session_id):
        return None

    def list_for_profile(self, search_profile_id, state):
        return tuple(
            p
            for p in self.proposals.values()
            if p.search_profile_id == search_profile_id and p.state == state
        )

    def mark_approved(self, proposal_id, key, *, profile_version=None, run_id=None):
        return None

    def mark_rejected(self, proposal_id, reason, rejection_at, rejection_note=None):
        proposal = self.proposals[proposal_id]
        updated = replace(
            proposal,
            state="rejected",
            rejection_reason=reason,
            rejection_note=rejection_note,
        )
        self.proposals[proposal_id] = updated
        return updated

    def mark_superseded(self, proposal_id, superseded_by, rejection_at):
        proposal = self.proposals[proposal_id]
        updated = replace(
            proposal,
            state="rejected",
            rejection_reason="edited",
            superseded_by_proposal_id=superseded_by,
        )
        self.proposals[proposal_id] = updated
        return updated

    def expire_pending(self, expired_before):
        return 0


class _Waiting:
    def __init__(self, run_id: UUID | None = None) -> None:
        self.run_id = run_id

    def active_for_session(self, session_id):
        if self.run_id is None:
            return None
        from types import SimpleNamespace

        return SimpleNamespace(run_id=self.run_id)


class _Radar:
    def __init__(self, profile: SearchProfile) -> None:
        self.profile = profile

    def validate_change(self, *, owner_id, profile_id, changes):
        return self.profile

    def update_profile(self, **kwargs):
        return self.profile, None


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
        current_version_id=UUID(int=120),
        latest_run_id=UUID(int=50),
        created_at=NOW,
        updated_at=NOW,
        correlation_id=CORRELATION_ID,
        actor_kind="service",
        actor_id=None,
    )


def _service(repo=None, waiting=None) -> tuple[SearchProfileUpdateProposals, _Repo]:
    storage = repo or _Repo()
    service = SearchProfileUpdateProposals(
        repository=storage,
        radar=_Radar(_profile()),
        events=_Events(),
        events_registry=load_events_registry(),
        ttl_hours=24,
        clock=lambda: NOW,
        waiting_runs=waiting,
    )
    return service, storage


def _pending(repo: _Repo, *, diff=None, base_version=3) -> Proposal:
    proposal = Proposal(
        proposal_id=uuid4(),
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        base_profile_version=base_version,
        diff=diff or {"budget_max": 900},
        impact={"fields_changed": ["budget_max"]},
        state="pending",
        expires_at=NOW + timedelta(hours=24),
        correlation_id=CORRELATION_ID,
    )
    repo.insert(proposal)
    return proposal


def test_reject_marks_user_reason_with_note() -> None:
    service, repo = _service()
    proposal = _pending(repo)
    rejected = service.reject(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        proposal_id=proposal.proposal_id,
        note="prefiero otra zona",
        correlation_id=CORRELATION_ID,
    )
    assert rejected.state == "rejected"
    assert rejected.rejection_reason == "user"
    assert rejected.rejection_note == "prefiero otra zona"


def test_reject_non_pending_is_rejected() -> None:
    service, repo = _service()
    proposal = _pending(repo)
    repo.proposals[proposal.proposal_id] = replace(
        proposal, state="approved", applied_idempotency_key="k"
    )
    with pytest.raises(ProposalNotPending):
        service.reject(
            user_id=USER_ID,
            session_id=SESSION_ID,
            search_profile_id=PROFILE_ID,
            proposal_id=proposal.proposal_id,
            note="x",
            correlation_id=CORRELATION_ID,
        )


def test_derive_creates_new_proposal_and_supersedes_original() -> None:
    service, repo = _service()
    original = _pending(repo)
    derived = service.derive(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        proposal_id=original.proposal_id,
        change={"budget_max": 1100},
        correlation_id=CORRELATION_ID,
    )
    assert derived.proposal_id != original.proposal_id
    assert derived.state == "pending"
    assert derived.base_profile_version == original.base_profile_version
    assert derived.diff == {"budget_max": 1100}
    # Original is never mutated: it becomes rejected('edited') with the link.
    stored_original = repo.proposals[original.proposal_id]
    assert stored_original.diff == {"budget_max": 900}
    assert stored_original.state == "rejected"
    assert stored_original.rejection_reason == "edited"
    assert stored_original.superseded_by_proposal_id == derived.proposal_id


def test_list_includes_waiting_run_id_for_pending() -> None:
    run_id = UUID(int=77)
    service, repo = _service(waiting=_Waiting(run_id))
    proposal = _pending(repo)
    listings = service.list(
        user_id=USER_ID, search_profile_id=PROFILE_ID, state="pending"
    )
    assert len(listings) == 1
    assert listings[0].proposal_id == proposal.proposal_id
    assert listings[0].waiting_run_id == run_id
    assert listings[0].session_id == SESSION_ID


def test_list_omits_waiting_run_when_no_active_run() -> None:
    service, repo = _service()
    _pending(repo)
    listings = service.list(
        user_id=USER_ID, search_profile_id=PROFILE_ID, state="pending"
    )
    assert len(listings) == 1
    assert listings[0].waiting_run_id is None


def test_derive_rejects_unknown_change_keys() -> None:
    service, repo = _service()
    original = _pending(repo)
    from umbral.application.agent.tools.contracts import ProposalInvalidChange

    with pytest.raises(ProposalInvalidChange):
        service.derive(
            user_id=USER_ID,
            session_id=SESSION_ID,
            search_profile_id=PROFILE_ID,
            proposal_id=original.proposal_id,
            change={"sql_injection": "x"},
            correlation_id=CORRELATION_ID,
        )
