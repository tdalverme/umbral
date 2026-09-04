# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Proposal tool contract tests (T026/T027): propose and apply via the executor."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID

from tests.support.agent import RecordingRunRecorder
from tests.support.tools import payload

from umbral.agent.tools.executor import ToolExecutor
from umbral.agent.tools.registry import ToolRegistry
from umbral.agent.tools.tools import ToolServices, build_tool_implementations
from umbral.application.agent.tools.contracts import Proposal
from umbral.application.agent.tools.ports import (
    ProposalRepository,
    SessionScope,
)
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.radar.contracts import SearchProfile
from umbral.application.agent.tools.preferences import (
    load_preference_vocabulary,
)

USER_ID = UUID(int=1)
SESSION_ID = UUID(int=2)
PROFILE_ID = UUID(int=5)
RUN_ID = UUID(int=10)
CORRELATION_ID = UUID(int=20)
NOW = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)


class _Repo:
    def __init__(self) -> None:
        self.proposals: dict[UUID, Proposal] = {}

    def insert(self, proposal: Proposal) -> Proposal:
        self.proposals[proposal.proposal_id] = proposal
        return proposal

    def get(self, proposal_id, session_id, user_id):
        return self.proposals.get(proposal_id)

    def latest_pending_for_profile(self, search_profile_id, session_id):
        return None

    def mark_approved(self, proposal_id, key, *, profile_version=None, run_id=None):
        proposal = self.proposals[proposal_id]
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
        proposal = self.proposals[proposal_id]
        updated = replace(proposal, state="rejected", rejection_reason=reason)
        self.proposals[proposal_id] = updated
        return updated

    def expire_pending(self, expired_before):
        return 0


class _Radar:
    def __init__(self) -> None:
        self.profile = _profile()
        self.applied = 0

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
        self.applied += 1
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
        self.events: list[object] = []

    def insert(self, event) -> None:
        self.events.append(event)


class _Other:
    pass


def _registry():
    import json
    from pathlib import Path

    from umbral.application.events.registry import parse_events_registry

    data = json.loads(
        Path("contracts/events/v1/events-registry.json").read_text(encoding="utf-8")
    )
    return parse_events_registry(data)


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


class _ScopeReader:
    def read_scope(self, user_id, session_id) -> SessionScope:
        return SessionScope(
            session_id=SESSION_ID, search_profile_id=PROFILE_ID, status="active"
        )


def _make_executor() -> tuple[ToolExecutor, _Repo, _Radar]:
    repo = _Repo()
    radar = _Radar()
    events = _Events()
    proposals = SearchProfileUpdateProposals(
        repository=cast(ProposalRepository, repo),
        radar=radar,
        events=events,
        events_registry=_registry(),
        ttl_hours=24,
        clock=lambda: NOW,
    )
    services = ToolServices(
        radar=_Other(),  # type: ignore[arg-type]
        scoring=_Other(),  # type: ignore[arg-type]
        feedback=_Other(),  # type: ignore[arg-type]
        criteria=_Other(),  # type: ignore[arg-type]
        proposals=proposals,
        vocabulary=load_preference_vocabulary(),
    )
    recorder = RecordingRunRecorder()
    executor = ToolExecutor(
        registry=ToolRegistry(_load_contract),
        implementations=build_tool_implementations(services),
        recorder=recorder,
        scope_reader=_ScopeReader(),
    )
    return executor, repo, radar


def _load_contract():
    from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract

    return load_tool_contract()


def _call(executor, name, args, *, confirmation=False):
    return executor.execute(
        user_id=USER_ID,
        session_id=SESSION_ID,
        run_id=RUN_ID,
        correlation_id=CORRELATION_ID,
        name=name,
        args=args,
        confirmation=confirmation,
    )


def test_propose_tool_creates_pending_proposal() -> None:
    executor, repo, _ = _make_executor()
    result = _call(
        executor,
        "propose_search_profile_update",
        {"change": {"budget_max": 200000}},
    )
    assert result.status == "ok"
    proposal_id = UUID(str(payload(result)["proposal_id"]))
    assert repo.proposals[proposal_id].state == "pending"


def test_propose_tool_accepts_canonical_change_keys() -> None:
    executor, repo, _ = _make_executor()
    result = _call(
        executor,
        "propose_search_profile_update",
        {"change": {"zona": "Palermo", "presupuesto": 200000}},
    )
    assert result.status == "ok"
    proposal_id = UUID(str(payload(result)["proposal_id"]))
    assert repo.proposals[proposal_id].diff == {
        "zones": ["palermo"],
        "budget_max": 200000.0,
    }


def test_propose_tool_rejects_unsupported_radio_with_clear_code() -> None:
    executor, _, _ = _make_executor()
    result = _call(
        executor,
        "propose_search_profile_update",
        {"change": {"zona": "Palermo", "radio": 1}},
    )
    assert result.status == "error"
    assert result.error_code == "proposal.unsupported_key"


def test_apply_tool_requires_confirmation() -> None:
    executor, repo, _ = _make_executor()
    proposal = Proposal(
        proposal_id=UUID(int=7),
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        base_profile_version=3,
        diff={"budget_max": 200000},
        impact={},
        state="pending",
        expires_at=NOW + timedelta(hours=1),
        correlation_id=CORRELATION_ID,
    )
    repo.proposals[proposal.proposal_id] = proposal
    result = _call(
        executor,
        "apply_search_profile_update",
        {
            "proposal_id": str(proposal.proposal_id),
            "confirmation": False,
            "idempotency_key": "k-1",
        },
    )
    # The executor gate fires before the implementation (FR-010).
    assert result.status == "error"
    assert result.error_code == "tool.confirmation_required"


def test_apply_tool_success_flow() -> None:
    executor, repo, radar = _make_executor()
    proposal = Proposal(
        proposal_id=UUID(int=8),
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        base_profile_version=3,
        diff={"budget_max": 200000},
        impact={},
        state="pending",
        expires_at=NOW + timedelta(hours=1),
        correlation_id=CORRELATION_ID,
    )
    repo.proposals[proposal.proposal_id] = proposal
    result = _call(
        executor,
        "apply_search_profile_update",
        {
            "proposal_id": str(proposal.proposal_id),
            "confirmation": True,
            "idempotency_key": "k-1",
        },
        confirmation=True,
    )
    assert result.status == "ok"
    assert result.result is not None
    assert payload(result)["state"] == "approved"
    assert payload(result)["profile_version"] == 4
    assert radar.applied == 1

