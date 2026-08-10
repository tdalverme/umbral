"""Durable search-profile update proposals service (H4.2, US3).

Propose produces a validated diff with impact and creates a durable pending
proposal (FR-007/FR-008); apply requires a valid proposal, explicit
confirmation and an idempotency key, versions the profile via the radar's
optimistic-lock path and triggers recomputation (FR-010/FR-011). State
transitions are deterministic only: approved via apply; rejected by
obsolescence (profile version moved past the proposal's base) or expiry
(clarification Q2, FR-009).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID, uuid4

from umbral.application.agent.tools.contracts import (
    AppliedProposal,
    Proposal,
    ProposalExpired,
    ProposalIdempotencyMismatch,
    ProposalInvalidChange,
    ProposalNotConfirmed,
    ProposalNotFound,
    ProposalNotPending,
    ProposalStale,
)
from umbral.application.agent.tools.ports import EventWriter, ProposalRepository
from umbral.application.events.contracts import ProductEvent
from umbral.application.events.registry import EventsRegistrySpec, event_version
from umbral.application.radar.contracts import SearchProfile
from umbral.domain.errors import ConcurrencyConflict

_ALLOWED_CHANGE_KEYS = {
    "name",
    "zones",
    "budget_max",
    "budget_min",
    "min_rooms",
    "surface_min",
    "surface_max",
}

Clock = Callable[[], datetime]


class RadarGateway(Protocol):
    """Radar surface: validate without persisting, then apply with the
    optimistic-lock path (H3-030). Both are implemented by RadarService."""

    def validate_change(
        self, *, owner_id: UUID, profile_id: UUID, changes: Mapping[str, object]
    ) -> SearchProfile: ...

    def update_profile(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        expected_version: int,
        changes: Mapping[str, object],
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> tuple[SearchProfile, object | None]: ...


class SearchProfileUpdateProposals:
    """Owns the durable proposal lifecycle (FR-008..FR-012)."""

    def __init__(
        self,
        *,
        repository: ProposalRepository,
        radar: RadarGateway,
        events: EventWriter,
        events_registry: EventsRegistrySpec,
        ttl_hours: int = 24,
        clock: Clock | None = None,
    ) -> None:
        self.repository = repository
        self.radar = radar
        self.events = events
        self.events_registry = events_registry
        self.ttl_hours = ttl_hours
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def propose(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        change: Mapping[str, object],
        correlation_id: UUID,
    ) -> Proposal:
        unknown = set(change) - _ALLOWED_CHANGE_KEYS
        if unknown:
            raise ProposalInvalidChange()
        profile = self.radar.validate_change(
            owner_id=user_id, profile_id=search_profile_id, changes=change
        )
        diff = {key: value for key, value in change.items()}
        impact = {
            "fields_changed": sorted(diff),
            "will_recompute": profile.status == "active",
        }
        proposal = Proposal(
            proposal_id=uuid4(),
            session_id=session_id,
            search_profile_id=search_profile_id,
            base_profile_version=profile.version,
            diff=diff,
            impact=impact,
            state="pending",
            expires_at=self.clock() + timedelta(hours=self.ttl_hours),
            correlation_id=correlation_id,
        )
        self.repository.insert(proposal)
        self._emit_server_event(
            event_type="search_profile.update_proposed.v1",
            actor_id=user_id,
            correlation_id=correlation_id,
            payload={
                "proposal_id": str(proposal.proposal_id),
                "search_profile_id": str(search_profile_id),
                "base_profile_version": proposal.base_profile_version,
            },
        )
        return proposal

    def apply(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        proposal_id: UUID,
        confirmation: bool,
        idempotency_key: str,
        correlation_id: UUID,
    ) -> AppliedProposal:
        if not confirmation:
            raise ProposalNotConfirmed()
        proposal = self._get_scoped(user_id, session_id, search_profile_id, proposal_id)
        if (
            proposal.applied_idempotency_key == idempotency_key
            and proposal.state == "approved"
        ):
            # Replay of the same key: return the recorded result, 0 duplicates
            # (FR-012, R-05).
            return AppliedProposal(
                proposal_id=proposal_id,
                state="approved",
                profile_version=proposal.applied_profile_version or 0,
                run_id=proposal.applied_run_id,
            )
        if proposal.state != "pending":
            raise ProposalNotPending()
        if proposal.expires_at < self.clock():
            self.repository.mark_rejected(proposal_id, "expired", self.clock())
            raise ProposalExpired()
        if proposal.applied_idempotency_key is not None:
            raise ProposalIdempotencyMismatch()
        try:
            updated, run = self.radar.update_profile(
                owner_id=user_id,
                profile_id=search_profile_id,
                expected_version=proposal.base_profile_version,
                changes=proposal.diff,
                correlation_id=correlation_id,
                actor_kind="user",
                actor_id=str(user_id),
            )
        except ConcurrencyConflict as exc:
            self.repository.mark_rejected(proposal_id, "obsolete", self.clock())
            raise ProposalStale() from exc
        run_id = getattr(run, "run_id", None)
        self.repository.mark_approved(
            proposal_id,
            idempotency_key,
            profile_version=updated.version,
            run_id=run_id,
        )
        self._emit_server_event(
            event_type="search_profile.update_applied.v1",
            actor_id=user_id,
            correlation_id=correlation_id,
            payload={
                "proposal_id": str(proposal_id),
                "search_profile_id": str(search_profile_id),
                "profile_version": updated.version,
            },
        )
        return AppliedProposal(
            proposal_id=proposal_id,
            state="approved",
            profile_version=updated.version,
            run_id=run_id,
        )

    def get(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        proposal_id: UUID,
    ) -> Proposal:
        return self._get_scoped(user_id, session_id, search_profile_id, proposal_id)

    def _get_scoped(
        self,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        proposal_id: UUID,
    ) -> Proposal:
        proposal = self.repository.get(proposal_id, session_id, user_id)
        if proposal is None or proposal.search_profile_id != search_profile_id:
            raise ProposalNotFound()
        return proposal

    def _emit_server_event(
        self,
        *,
        event_type: str,
        actor_id: UUID,
        correlation_id: UUID,
        payload: Mapping[str, object],
    ) -> None:
        version = event_version(self.events_registry, event_type)
        self.events.insert(
            ProductEvent(
                event_id=uuid4(),
                event_type=event_type,
                event_version=version or 1,
                actor_id=actor_id,
                occurred_at=self.clock(),
                correlation_id=correlation_id,
                payload=dict(payload),
            )
        )
