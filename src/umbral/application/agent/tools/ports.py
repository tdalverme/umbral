"""Ports for the durable proposal service and tool scope (H4.2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from umbral.application.agent.tools.contracts import Proposal
from umbral.application.events.contracts import ProductEvent


class EventWriter(Protocol):
    """Persists a validated product event (DoD #4)."""

    def insert(self, event: ProductEvent) -> None: ...


class ProposalRepository(Protocol):
    """Persistence for durable proposals (FR-008)."""

    def insert(self, proposal: Proposal) -> Proposal: ...

    def enqueue_pending(self, proposal: Proposal) -> Proposal:
        """Insert a pending proposal and assign its queue position atomically."""

    def supersede_and_insert(
        self, proposal_id: UUID, successor: Proposal
    ) -> Proposal | None:
        """Atomically replace a pending proposal with its derived successor."""

    def get(
        self, proposal_id: UUID, session_id: UUID, user_id: UUID
    ) -> Proposal | None:
        """Scoped lookup: only the owning user/session may read a proposal."""

    def latest_pending_for_profile(
        self, search_profile_id: UUID, session_id: UUID
    ) -> Proposal | None: ...

    def pending_for_profile(
        self, search_profile_id: UUID, session_id: UUID
    ) -> tuple[Proposal, ...]: ...

    def list_for_profile(
        self,
        search_profile_id: UUID,
        state: str,
    ) -> tuple[Proposal, ...]:
        """List proposals of a radar in a given state (R-09).

        Ownership is guaranteed by the caller: the radar belongs to the
        authenticated user (product.search_profile.read scope).
        """

    def mark_approved(
        self,
        proposal_id: UUID,
        applied_idempotency_key: str,
        *,
        profile_version: int | None = None,
        run_id: UUID | None = None,
    ) -> Proposal | None: ...

    def mark_rejected(
        self,
        proposal_id: UUID,
        rejection_reason: str,
        rejection_at: datetime,
        rejection_note: str | None = None,
    ) -> Proposal | None: ...

    def mark_superseded(
        self,
        proposal_id: UUID,
        superseded_by_proposal_id: UUID,
        rejection_at: datetime,
    ) -> Proposal | None:
        """Mark the original as rejected('edited') and link its successor."""

    def rebase_pending_for_queue(
        self, search_profile_id: UUID, session_id: UUID, base_profile_version: int
    ) -> None: ...

    def expire_pending(self, expired_before: datetime) -> int:
        """Mark every pending proposal past the window as rejected('expired').

        Deterministic maintenance path (R-11); idempotent.
        """


class WaitingRunReader(Protocol):
    """Finds the non-terminal run of a session (the waiting HITL run)."""

    def active_for_session(self, session_id: UUID) -> object | None: ...


@dataclass(frozen=True, slots=True)
class SessionScope:
    """Resolved scope of a session: its radar and status."""

    session_id: UUID
    search_profile_id: UUID
    status: str


class ProposalDecisionGateway(Protocol):
    """HITL decision seam consumed by the graph (R-04/R-05).

    The graph never touches repositories directly: it fetches proposal
    payloads, applies interactive rejection and derives edited proposals.
    """

    def get(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        proposal_id: UUID,
    ) -> Proposal: ...

    def reject(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        proposal_id: UUID,
        note: str,
        correlation_id: UUID,
    ) -> Proposal: ...

    def derive(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        proposal_id: UUID,
        change: Mapping[str, object],
        correlation_id: UUID,
    ) -> Proposal: ...


class PreferenceDecisionGateway(Protocol):
    """HITL decision seam for preference proposals (014-soft-preferences-chat).

    Implemented by the feedback service over durable learning proposals: the
    graph only fetches payloads, confirms (fact + recompute) and rejects.
    """

    def get_proposal(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        proposal_id: UUID,
    ) -> object: ...

    def confirm_proposal(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        proposal_id: UUID,
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> object: ...

    def confirm_preference_removal(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        proposal_id: UUID,
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> object: ...

    def reject_proposal(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        proposal_id: UUID,
        correlation_id: UUID,
        actor_id: str | None = None,
    ) -> object: ...


class SessionScopeReader(Protocol):
    """Resolves a session's scope for an authenticated user (FR-002)."""

    def read_scope(self, user_id: UUID, session_id: UUID) -> SessionScope | None: ...


@dataclass(frozen=True, slots=True)
class Scope:
    """The resolved context a tool may operate within."""

    user_id: UUID
    session_id: UUID
    search_profile_id: UUID
    diff: Mapping[str, object] | None = None
