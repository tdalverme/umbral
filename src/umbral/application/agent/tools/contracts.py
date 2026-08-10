"""Durable search-profile update proposals (H4.2, US3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

ProposalState = Literal["pending", "approved", "rejected"]
ProposalRejectionReason = Literal["obsolete", "expired", "user", "edited"]


@dataclass(frozen=True, slots=True)
class ProposalChange:
    """A requested profile change: structured fields plus the base version."""

    fields: Mapping[str, object]
    base_profile_version: int


@dataclass(frozen=True, slots=True)
class Proposal:
    """Durable, auditable proposal with interactive lifecycle (FR-008, R-05)."""

    proposal_id: UUID
    session_id: UUID
    search_profile_id: UUID
    base_profile_version: int
    diff: Mapping[str, object]
    impact: Mapping[str, object]
    state: ProposalState
    expires_at: datetime
    applied_idempotency_key: str | None = None
    rejection_reason: ProposalRejectionReason | None = None
    applied_profile_version: int | None = None
    applied_run_id: UUID | None = None
    correlation_id: UUID | None = None
    rejection_note: str | None = None
    superseded_by_proposal_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ProposalListing:
    """A proposal row as the structured UI needs it (FR-033, R-09)."""

    proposal_id: UUID
    session_id: UUID
    search_profile_id: UUID
    state: ProposalState
    diff: Mapping[str, object]
    impact: Mapping[str, object]
    expires_at: datetime
    rejection_reason: ProposalRejectionReason | None = None
    rejection_note: str | None = None
    superseded_by_proposal_id: UUID | None = None
    waiting_run_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class AppliedProposal:
    """Result of applying a proposal (FR-010/FR-011)."""

    proposal_id: UUID
    state: ProposalState
    profile_version: int
    run_id: UUID | None = None


class ProposalError(Exception):
    """Base class for sanitized proposal failures."""

    code = "proposal.error"


class ProposalNotFound(ProposalError):
    """No proposal exists with that id in the caller's scope."""

    code = "proposal.not_found"


class ProposalNotPending(ProposalError):
    """The proposal is no longer pending (already used or rejected)."""

    code = "proposal.not_pending"


class ProposalExpired(ProposalError):
    """The proposal is past its expiry window."""

    code = "proposal.expired"


class ProposalNotConfirmed(ProposalError):
    """Apply was attempted without the explicit confirmation flag."""

    code = "proposal.not_confirmed"


class ProposalStale(ProposalError):
    """The profile changed since the proposal's base version (obsolescence)."""

    code = "proposal.stale"


class ProposalIdempotencyMismatch(ProposalError):
    """A different idempotency key was replayed against a used proposal."""

    code = "proposal.idempotency_mismatch"


class ProposalInvalidChange(ProposalError):
    """The requested change failed profile/policy validation."""

    code = "proposal.invalid_change"
