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

import unicodedata
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
    ProposalListing,
    ProposalNotConfirmed,
    ProposalNotFound,
    ProposalNotPending,
    ProposalStale,
    ProposalUnsupportedChange,
)
from umbral.application.agent.tools.ports import (
    EventWriter,
    ProposalRepository,
    WaitingRunReader,
)
from umbral.application.events.contracts import ProductEvent
from umbral.application.events.registry import EventsRegistrySpec, event_version
from umbral.application.radar.contracts import (
    RadarStateError,
    RadarValidationError,
    SearchProfile,
)
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

# Canonical chat vocabulary mapped deterministically onto profile fields; the
# LLM never picks profile field names (0 guessing, auditable translation).
_CANONICAL_CHANGE_KEYS = {
    "zona": "zones",
    "budget": "budget_max",
    "presupuesto": "budget_max",
    "precio": "budget_max",
    "ambientes": "min_rooms",
    "habitaciones": "min_rooms",
    "rooms": "min_rooms",
    "superficie": "surface_min",
    "metros": "surface_min",
    "metros_cuadrados": "surface_min",
    "m2": "surface_min",
}

# High-impact criteria without a supporting profile field: rejected with an
# actionable code so the agent explains what it can actually change.
_UNSUPPORTED_CHANGE_KEYS = frozenset({"radio", "hard_filters"})

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
        waiting_runs: WaitingRunReader | None = None,
    ) -> None:
        self.repository = repository
        self.radar = radar
        self.events = events
        self.events_registry = events_registry
        self.ttl_hours = ttl_hours
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.waiting_runs = waiting_runs

    def propose(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        change: Mapping[str, object],
        correlation_id: UUID,
        source_act_id: str = "",
    ) -> Proposal:
        profile_change = _normalize_change(change)
        profile = self._validate(
            user_id=user_id,
            search_profile_id=search_profile_id,
            change=profile_change,
        )
        diff = {key: value for key, value in profile_change.items()}
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
            source_act_id=source_act_id or "legacy",
            queue_ordinal=1,
            queue_total=1,
        )
        proposal = self.repository.enqueue_pending(proposal)
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
            self.repository.reject_pending(proposal_id, "expired", self.clock())
            raise ProposalExpired()
        if proposal.applied_idempotency_key is not None:
            raise ProposalIdempotencyMismatch()
        def update_radar(current: Proposal) -> tuple[int, UUID | None]:
            updated, run = self.radar.update_profile(
                owner_id=user_id,
                profile_id=search_profile_id,
                expected_version=current.base_profile_version,
                changes=current.diff,
                correlation_id=correlation_id,
                actor_kind="user",
                actor_id=str(user_id),
            )
            return updated.version, getattr(run, "run_id", None)

        try:
            stored = self.repository.apply_pending(
                proposal_id, idempotency_key, update_radar
            )
        except ConcurrencyConflict as exc:
            self.repository.reject_pending(proposal_id, "obsolete", self.clock())
            raise ProposalStale() from exc
        if stored is None:
            raise ProposalNotFound()
        if stored.state != "approved":
            raise ProposalNotPending()
        if stored.applied_idempotency_key != idempotency_key:
            raise ProposalIdempotencyMismatch()
        profile_version = stored.applied_profile_version or 0
        run_id = stored.applied_run_id
        self.repository.rebase_pending_for_queue(
            search_profile_id, session_id, profile_version
        )
        self._emit_server_event(
            event_type="search_profile.update_applied.v1",
            actor_id=user_id,
            correlation_id=correlation_id,
            payload={
                "proposal_id": str(proposal_id),
                "search_profile_id": str(search_profile_id),
                "profile_version": profile_version,
            },
        )
        return AppliedProposal(
            proposal_id=proposal_id,
            state="approved",
            profile_version=profile_version,
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

    def reject(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        proposal_id: UUID,
        note: str,
        correlation_id: UUID,
    ) -> Proposal:
        """Interactive rejection: pending → rejected('user') with the user's
        bounded note; 0 effects on the profile (FR-013, R-05)."""
        proposal = self._get_scoped(user_id, session_id, search_profile_id, proposal_id)
        if proposal.state != "pending":
            raise ProposalNotPending()
        stored = self.repository.reject_pending(
            proposal_id,
            "user",
            self.clock(),
            rejection_note=(note[:200] if note else None),
        )
        if stored is None:
            raise ProposalNotFound()
        return stored

    def derive(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        proposal_id: UUID,
        change: Mapping[str, object],
        correlation_id: UUID,
        source_act_id: str = "",
    ) -> Proposal:
        """Edit as a NEW derived proposal (clarification Q2, FR-014, R-05).

        The original is marked ``rejected('edited')`` with
        ``superseded_by_proposal_id`` pointing to the derived pending
        proposal; the original diff is never mutated (0 reescrituras).
        """
        original = self._get_scoped(user_id, session_id, search_profile_id, proposal_id)
        if original.state != "pending":
            raise ProposalNotPending()
        profile_change = _normalize_change(change)
        profile = self._validate(
            user_id=user_id,
            search_profile_id=search_profile_id,
            change=profile_change,
        )
        diff = {key: value for key, value in profile_change.items()}
        derived = Proposal(
            proposal_id=uuid4(),
            session_id=session_id,
            search_profile_id=search_profile_id,
            base_profile_version=profile.version,
            diff=diff,
            impact={
                "fields_changed": sorted(diff),
                "will_recompute": profile.status == "active",
            },
            state="pending",
            expires_at=self.clock() + timedelta(hours=self.ttl_hours),
            correlation_id=correlation_id,
            source_act_id=source_act_id or original.source_act_id,
            queue_ordinal=original.queue_ordinal,
            queue_total=original.queue_total,
        )
        stored = self.repository.supersede_and_insert(proposal_id, derived)
        if stored is None:
            raise ProposalNotPending()
        derived = stored
        self._emit_server_event(
            event_type="search_profile.update_proposed.v1",
            actor_id=user_id,
            correlation_id=correlation_id,
            payload={
                "proposal_id": str(derived.proposal_id),
                "search_profile_id": str(search_profile_id),
                "base_profile_version": derived.base_profile_version,
            },
        )
        return derived

    def _next_queue_ordinal(
        self, search_profile_id: UUID, session_id: UUID
    ) -> int:
        entries = self.repository.pending_for_profile(search_profile_id, session_id)
        return max((proposal.queue_ordinal for proposal in entries), default=0) + 1

    def pending_for_session(
        self, *, search_profile_id: UUID, session_id: UUID
    ) -> tuple[Proposal, ...]:
        """Return the durable confirmation queue in its published order."""
        return self.repository.pending_for_profile(search_profile_id, session_id)

    def list(
        self,
        *,
        user_id: UUID,
        search_profile_id: UUID,
        state: str,
    ) -> tuple[ProposalListing, ...]:
        """Scoped proposal list with the waiting HITL run per proposal (R-09)."""
        proposals = self.repository.list_for_profile(search_profile_id, state)
        listings: list[ProposalListing] = []
        for proposal in proposals:
            waiting_run_id = None
            if (
                proposal.state == "pending"
                and self.waiting_runs is not None
            ):
                run = self.waiting_runs.active_for_session(proposal.session_id)
                if run is not None:
                    waiting_run_id = getattr(run, "run_id", None)
            listings.append(
                ProposalListing(
                    proposal_id=proposal.proposal_id,
                    session_id=proposal.session_id,
                    search_profile_id=proposal.search_profile_id,
                    state=proposal.state,
                    diff=proposal.diff,
                    impact=proposal.impact,
                    expires_at=proposal.expires_at,
                    rejection_reason=proposal.rejection_reason,
                    rejection_note=proposal.rejection_note,
                    superseded_by_proposal_id=proposal.superseded_by_proposal_id,
                    waiting_run_id=waiting_run_id,
                )
            )
        return tuple(listings)

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

    def _validate(
        self, *, user_id: UUID, search_profile_id: UUID, change: Mapping[str, object]
    ) -> SearchProfile:
        try:
            return self.radar.validate_change(
                owner_id=user_id,
                profile_id=search_profile_id,
                changes=change,
            )
        except (RadarValidationError, RadarStateError) as exc:
            raise ProposalInvalidChange() from exc

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


def _normalize_change(change: Mapping[str, object]) -> dict[str, object]:
    """Map the canonical chat vocabulary onto profile fields (deterministic).

    Canonical keys (zona, presupuesto, ambientes, superficie...) are translated
    to profile fields with value normalization (zone codes without accents or
    case); profile field names pass through untouched. Unsupported criteria
    (radio, hard_filters) raise ``ProposalUnsupportedChange``; unknown keys
    raise ``ProposalInvalidChange``.
    """
    unsupported = set(change) & _UNSUPPORTED_CHANGE_KEYS
    if unsupported:
        raise ProposalUnsupportedChange(sorted(unsupported)[0])
    translated: dict[str, object] = {}
    for key, value in change.items():
        target = _CANONICAL_CHANGE_KEYS.get(key, key)
        translated[target] = _normalize_value(target, value)
    unknown = set(translated) - _ALLOWED_CHANGE_KEYS
    if unknown:
        raise ProposalInvalidChange()
    return translated


def _normalize_value(field: str, value: object) -> object:
    if field == "zones":
        return _normalize_zones(value)
    if field == "min_rooms":
        return _as_int(value)
    if field in {"budget_max", "budget_min", "surface_min", "surface_max"}:
        return _as_number(value)
    return value


def _normalize_zones(value: object) -> list[str]:
    raw = value if isinstance(value, list) else [value]
    zones: list[str] = []
    for item in raw:
        if item is None:
            continue
        if not isinstance(item, str):
            raise ProposalInvalidChange()
        code = _zone_code(item)
        if not code:
            raise ProposalInvalidChange()
        zones.append(code)
    return zones


def _zone_code(name: str) -> str:
    code = name.strip().lower()
    code = "".join(
        char
        for char in unicodedata.normalize("NFD", code)
        if unicodedata.category(char) != "Mn"
    )
    return code.replace(" ", "_")


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        raise ProposalInvalidChange()
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ProposalInvalidChange()


def _as_number(value: object) -> float:
    if isinstance(value, bool):
        raise ProposalInvalidChange()
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            raise ProposalInvalidChange() from None
    raise ProposalInvalidChange()
