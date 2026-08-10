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

    def get(
        self, proposal_id: UUID, session_id: UUID, user_id: UUID
    ) -> Proposal | None:
        """Scoped lookup: only the owning user/session may read a proposal."""

    def latest_pending_for_profile(
        self, search_profile_id: UUID, session_id: UUID
    ) -> Proposal | None: ...

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
    ) -> Proposal | None: ...

    def expire_pending(self, expired_before: datetime) -> int:
        """Mark every pending proposal past the window as rejected('expired').

        Deterministic maintenance path (R-11); idempotent.
        """


@dataclass(frozen=True, slots=True)
class SessionScope:
    """Resolved scope of a session: its radar and status."""

    session_id: UUID
    search_profile_id: UUID
    status: str


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
