# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Proposal service lifecycle tests (FR-007..FR-012, T020)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID

import pytest

from umbral.application.agent.tools.contracts import (
    Proposal,
    ProposalExpired,
    ProposalInvalidChange,
    ProposalNotFound,
    ProposalNotPending,
    ProposalStale,
    ProposalUnsupportedChange,
)
from umbral.application.agent.tools.ports import ProposalRepository
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.events.contracts import ProductEvent
from umbral.application.events.registry import parse_events_registry
from umbral.application.radar.contracts import RadarValidationError, SearchProfile

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

    def enqueue_pending(self, proposal: Proposal) -> Proposal:
        ordinal = (
            max(
                (
                    item.queue_ordinal
                    for item in self.proposals.values()
                    if item.search_profile_id == proposal.search_profile_id
                    and item.session_id == proposal.session_id
                    and item.state == "pending"
                ),
                default=0,
            )
            + 1
        )
        for proposal_id, item in tuple(self.proposals.items()):
            if (
                item.search_profile_id == proposal.search_profile_id
                and item.session_id == proposal.session_id
                and item.state == "pending"
            ):
                self.proposals[proposal_id] = replace(item, queue_total=ordinal)
        queued = replace(proposal, queue_ordinal=ordinal, queue_total=ordinal)
        self.proposals[queued.proposal_id] = queued
        return queued

    def get(self, proposal_id, session_id, user_id) -> Proposal | None:
        return self.proposals.get(proposal_id)

    def latest_pending_for_profile(self, search_profile_id, session_id):
        return None

    def pending_for_profile(self, search_profile_id, session_id):
        return tuple(
            sorted(
                (
                    proposal
                    for proposal in self.proposals.values()
                    if proposal.search_profile_id == search_profile_id
                    and proposal.session_id == session_id
                    and proposal.state == "pending"
                ),
                key=lambda proposal: proposal.queue_ordinal,
            )
        )

    def list_for_profile(self, search_profile_id, state):
        return tuple(
            proposal
            for proposal in self.proposals.values()
            if proposal.search_profile_id == search_profile_id
            and proposal.state == state
        )

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

    def mark_rejected(self, proposal_id, reason, rejection_at, rejection_note=None):
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            return None
        updated = replace(
            proposal,
            state="rejected",
            rejection_reason=reason,
            rejection_note=rejection_note,
        )
        self.proposals[proposal_id] = updated
        return updated

    def apply_pending(self, proposal_id, key, operation):
        proposal = self.proposals.get(proposal_id)
        if proposal is None or proposal.state != "pending":
            return proposal
        profile_version, run_id = operation(proposal)
        updated = replace(
            proposal,
            state="approved",
            applied_idempotency_key=key,
            applied_profile_version=profile_version,
            applied_run_id=run_id,
        )
        self.proposals[proposal_id] = updated
        return updated

    def reject_pending(self, proposal_id, reason, rejection_at, rejection_note=None):
        proposal = self.proposals.get(proposal_id)
        if proposal is None or proposal.state != "pending":
            return proposal
        return self.mark_rejected(proposal_id, reason, rejection_at, rejection_note)

    def mark_superseded(self, proposal_id, successor_id, rejection_at):
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            return None
        updated = replace(
            proposal,
            state="rejected",
            rejection_reason="edited",
            superseded_by_proposal_id=successor_id,
        )
        self.proposals[proposal_id] = updated
        return updated

    def supersede_and_insert(self, proposal_id, successor):
        original = self.proposals.get(proposal_id)
        if original is None or original.state != "pending":
            return None
        self.proposals[proposal_id] = replace(
            original,
            state="rejected",
            rejection_reason="edited",
            superseded_by_proposal_id=successor.proposal_id,
        )
        self.proposals[successor.proposal_id] = successor
        return successor

    def rebase_pending_for_queue(self, search_profile_id, session_id, version):
        for proposal_id, proposal in tuple(self.proposals.items()):
            if (
                proposal.search_profile_id == search_profile_id
                and proposal.session_id == session_id
                and proposal.state == "pending"
            ):
                self.proposals[proposal_id] = replace(
                    proposal, base_profile_version=version
                )

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
        repository=cast(ProposalRepository, repo),
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


def test_pending_proposals_keep_original_act_order() -> None:
    service, repo, _, _ = _make_service()
    zones = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"zones": ["palermo"]},
        correlation_id=CORRELATION_ID,
        source_act_id="zones",
    )
    budget = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"budget_max": 1200},
        correlation_id=CORRELATION_ID,
        source_act_id="budget",
    )

    assert [
        (item.source_act_id, item.queue_ordinal)
        for item in repo.pending_for_profile(PROFILE_ID, SESSION_ID)
    ] == [("zones", 1), ("budget", 2)]
    assert zones.queue_ordinal == 1
    assert budget.queue_ordinal == 2


def test_approving_a_queue_step_rebases_only_the_remaining_steps() -> None:
    service, repo, _, _ = _make_service()
    first = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"zones": ["palermo"]},
        correlation_id=CORRELATION_ID,
    )
    second = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"budget_max": 1200},
        correlation_id=CORRELATION_ID,
    )

    service.apply(**_base_args(first.proposal_id))

    assert repo.proposals[first.proposal_id].state == "approved"
    assert repo.proposals[second.proposal_id].state == "pending"
    assert repo.proposals[second.proposal_id].base_profile_version == 4


def test_rejecting_a_queue_step_exposes_the_next_head() -> None:
    service, repo, _, _ = _make_service()
    first = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"zones": ["palermo"]},
        correlation_id=CORRELATION_ID,
    )
    second = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"budget_max": 1200},
        correlation_id=CORRELATION_ID,
    )

    service.reject(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        proposal_id=first.proposal_id,
        note="no",
        correlation_id=CORRELATION_ID,
    )

    remaining = repo.pending_for_profile(PROFILE_ID, SESSION_ID)
    assert remaining == (repo.proposals[second.proposal_id],)
    assert remaining[0].queue_ordinal == 2
    assert remaining[0].queue_total == 2


def test_queue_total_remains_coherent_after_consuming_the_head() -> None:
    service, repo, _, _ = _make_service()
    first = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"zones": ["palermo"]},
        correlation_id=CORRELATION_ID,
    )
    second = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"budget_max": 1200},
        correlation_id=CORRELATION_ID,
    )

    assert repo.proposals[first.proposal_id].queue_total == 2
    assert second.queue_total == 2
    service.apply(**_base_args(first.proposal_id))
    remaining = repo.proposals[second.proposal_id]
    assert remaining.queue_ordinal == 2
    assert remaining.queue_total == 2


def test_apply_uses_atomic_pending_resolution_port() -> None:
    service, repo, radar, _ = _make_service()
    proposal = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"budget_max": 1200},
        correlation_id=CORRELATION_ID,
    )
    calls: list[Proposal] = []

    def apply_pending(proposal_id, key, operation):
        current = repo.proposals[proposal_id]
        calls.append(current)
        version, run_id = operation(current)
        updated = replace(
            current,
            state="approved",
            applied_idempotency_key=key,
            applied_profile_version=version,
            applied_run_id=run_id,
        )
        repo.proposals[proposal_id] = updated
        return updated

    repo.apply_pending = apply_pending  # type: ignore[attr-defined]
    service.apply(**_base_args(proposal.proposal_id))

    assert calls == [proposal]
    assert len(radar.applied) == 1


def test_propose_uses_atomic_enqueue_port_when_available() -> None:
    service, repo, _, _ = _make_service()
    calls: list[Proposal] = []

    def enqueue_pending(proposal: Proposal) -> Proposal:
        calls.append(proposal)
        queued = replace(proposal, queue_ordinal=7, queue_total=9)
        repo.proposals[queued.proposal_id] = queued
        return queued

    repo.enqueue_pending = enqueue_pending  # type: ignore[attr-defined]
    proposal = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"budget_max": 1200},
        correlation_id=CORRELATION_ID,
    )

    assert calls
    assert proposal.queue_ordinal == 7
    assert proposal.queue_total == 9


def test_correction_derives_a_traceable_proposal_at_the_same_queue_position() -> None:
    service, repo, _, _ = _make_service()
    original = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"zones": ["palermo"]},
        correlation_id=CORRELATION_ID,
        source_act_id="palermo",
    )
    corrected = service.derive(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        proposal_id=original.proposal_id,
        change={"zones": ["belgrano"]},
        correlation_id=CORRELATION_ID,
        source_act_id="belgrano",
    )

    assert (
        repo.proposals[original.proposal_id].superseded_by_proposal_id
        == corrected.proposal_id
    )
    assert corrected.queue_ordinal == original.queue_ordinal == 1
    assert corrected.source_act_id == "belgrano"


def test_correction_uses_atomic_supersession_port_when_available() -> None:
    service, repo, _, _ = _make_service()
    original = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"zones": ["palermo"]},
        correlation_id=CORRELATION_ID,
    )
    calls: list[tuple[UUID, Proposal]] = []

    def supersede_and_insert(original_id: UUID, successor: Proposal) -> Proposal:
        calls.append((original_id, successor))
        repo.proposals[original_id] = replace(
            repo.proposals[original_id],
            state="rejected",
            rejection_reason="edited",
            superseded_by_proposal_id=successor.proposal_id,
        )
        repo.proposals[successor.proposal_id] = successor
        return successor

    repo.supersede_and_insert = supersede_and_insert  # type: ignore[attr-defined]
    corrected = service.derive(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        proposal_id=original.proposal_id,
        change={"zones": ["belgrano"]},
        correlation_id=CORRELATION_ID,
        source_act_id="belgrano",
    )

    assert calls and calls[0][0] == original.proposal_id
    assert (
        repo.proposals[original.proposal_id].superseded_by_proposal_id
        == corrected.proposal_id
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


def test_propose_translates_canonical_zone_to_profile_zones() -> None:
    service, _, _, _ = _make_service()
    proposal = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"zona": "Palermo"},
        correlation_id=CORRELATION_ID,
    )
    assert proposal.diff == {"zones": ["palermo"]}


def test_propose_normalizes_zone_names_accents_and_case() -> None:
    service, _, _, _ = _make_service()
    proposal = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"zona": ["Nuñez", "VILLA CRESPO", "San Nicolás"]},
        correlation_id=CORRELATION_ID,
    )
    assert proposal.diff == {"zones": ["nunez", "villa_crespo", "san_nicolas"]}


def test_propose_translates_budget_ambientes_superficie() -> None:
    service, _, _, _ = _make_service()
    proposal = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={
            "presupuesto": "900000",
            "ambientes": 3,
            "superficie": "55",
        },
        correlation_id=CORRELATION_ID,
    )
    assert proposal.diff == {
        "budget_max": 900000.0,
        "min_rooms": 3,
        "surface_min": 55.0,
    }


def test_propose_mixes_canonical_and_profile_keys() -> None:
    service, _, _, _ = _make_service()
    proposal = service.propose(
        user_id=USER_ID,
        session_id=SESSION_ID,
        search_profile_id=PROFILE_ID,
        change={"zona": "Belgrano", "budget_max": 200000},
        correlation_id=CORRELATION_ID,
    )
    assert proposal.diff == {"zones": ["belgrano"], "budget_max": 200000.0}


def test_propose_rejects_unsupported_criteria_with_actionable_code() -> None:
    service, _, _, _ = _make_service()
    with pytest.raises(ProposalUnsupportedChange) as excinfo:
        service.propose(
            user_id=USER_ID,
            session_id=SESSION_ID,
            search_profile_id=PROFILE_ID,
            change={"zona": "Palermo", "radio": 1},
            correlation_id=CORRELATION_ID,
        )
    assert excinfo.value.key == "radio"
    with pytest.raises(ProposalUnsupportedChange) as excinfo:
        service.propose(
            user_id=USER_ID,
            session_id=SESSION_ID,
            search_profile_id=PROFILE_ID,
            change={"hard_filters": {"min_floor": 5}},
            correlation_id=CORRELATION_ID,
        )
    assert excinfo.value.key == "hard_filters"


def test_propose_rejects_non_numeric_budget_value() -> None:
    service, _, _, _ = _make_service()
    with pytest.raises(ProposalInvalidChange):
        service.propose(
            user_id=USER_ID,
            session_id=SESSION_ID,
            search_profile_id=PROFILE_ID,
            change={"presupuesto": "alto"},
            correlation_id=CORRELATION_ID,
        )


def test_propose_rejects_non_string_zone_value() -> None:
    service, _, _, _ = _make_service()
    with pytest.raises(ProposalInvalidChange):
        service.propose(
            user_id=USER_ID,
            session_id=SESSION_ID,
            search_profile_id=PROFILE_ID,
            change={"zona": 5},
            correlation_id=CORRELATION_ID,
        )


def test_propose_maps_radar_validation_errors_to_invalid_change() -> None:
    service, _, radar, _ = _make_service()

    def boom(*, owner_id, profile_id, changes):
        raise RadarValidationError(("radar.zone_unknown",))

    radar.validate_change = boom  # type: ignore[method-assign]
    with pytest.raises(ProposalInvalidChange):
        service.propose(
            user_id=USER_ID,
            session_id=SESSION_ID,
            search_profile_id=PROFILE_ID,
            change={"zones": ("tigre",)},
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
