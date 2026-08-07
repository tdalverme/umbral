"""Pure, transport-independent values and errors for feedback and learning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from umbral.application.silver.contracts import NormalizedListing

FeedbackEventType = Literal["like", "dislike", "save", "dismiss", "contacted"]
FeedbackEventState = Literal["active", "superseded"]
DecisionState = Literal["like", "dislike", "save", "dismiss", "contacted", "none"]
Polarity = Literal["positive", "negative", "neutral"]
ProposalState = Literal["pending", "confirmed", "rejected", "expired", "superseded"]

_EVENT_TYPES = {"like", "dislike", "save", "dismiss", "contacted"}
_POLARITIES = {"positive", "negative", "neutral"}
_PROPOSAL_STATES = {"pending", "confirmed", "rejected", "expired", "superseded"}


@dataclass(frozen=True, slots=True)
class ReasonRef:
    """One quick reason attached to a feedback event."""

    reason_key: str
    polarity: Polarity
    concept_key: str | None


@dataclass(frozen=True, slots=True)
class FeedbackEvent:
    """Immutable, append-only record of one user decision (FR-001/FR-002)."""

    event_id: UUID
    profile_id: UUID
    listing_id: UUID
    run_id: UUID | None
    event_type: FeedbackEventType
    state: FeedbackEventState
    superseded_by: UUID | None
    idempotency_key: str
    reasons: tuple[ReasonRef, ...]
    free_feedback: str | None
    created_at: datetime
    correlation_id: UUID
    actor_kind: str = "service"
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class DecisionStateRow:
    """Derived decision state for one (profile, listing) from the active event."""

    decision_state: DecisionState
    event_id: UUID | None
    event_type: FeedbackEventType | None
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class DecisionItem:
    """One listing with its current decision state for the shortlist/dismissed views."""

    listing_id: UUID
    decision_state: DecisionState
    event_id: UUID
    event_type: FeedbackEventType
    reason_keys: tuple[str, ...]
    created_at: datetime
    summary: NormalizedListing | None = None


@dataclass(frozen=True, slots=True)
class FeedbackRecord:
    """Result of recording one feedback action."""

    event: FeedbackEvent
    decision_state: DecisionState
    superseded: bool
    noop: bool


@dataclass(frozen=True, slots=True)
class QuickReason:
    """One curated quick-reason category from the versioned seed (FR-006)."""

    key: str
    label: str
    polarity: Polarity
    concept_key: str | None
    allowed_on: tuple[FeedbackEventType, ...]

    def allowed_for(self, event_type: FeedbackEventType) -> bool:
        return event_type in self.allowed_on


@dataclass(frozen=True, slots=True)
class QuickReasonsSpec:
    """Validated quick-reasons seed."""

    registry_version: str
    contract_version: str
    reasons: tuple[QuickReason, ...]

    def by_key(self) -> Mapping[str, QuickReason]:
        return {reason.key: reason for reason in self.reasons}


@dataclass(frozen=True, slots=True)
class LearningPolicyDoc:
    """Validated, executable interpretation of one learning policy version."""

    contract_version: str
    learning_policy_version: str
    min_signals: int
    window_days: int
    min_signal_confidence: float
    cooldown_days: int
    proposal_expiration_days: int
    default_suggested_weight: float
    default_suggested_confidence: float


@dataclass(frozen=True, slots=True)
class LearningPolicyVersion:
    """Immutable version of a learning policy document (FR-009)."""

    version_id: UUID
    policy_id: UUID
    policy_version: int
    contract_version: str
    payload: Mapping[str, object]
    created_at: datetime
    correlation_id: UUID
    actor_kind: str = "service"
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProposalDraft:
    """Pure outcome of the signal engine (US3)."""

    concept_key: str
    polarity: str
    evidence_event_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ProposalChange:
    """Editable proposal content; kind preference_fact in v1 (R-06)."""

    kind: Literal["preference_fact"]
    concept_key: str
    polarity: str
    suggested_weight: float
    suggested_confidence: float
    value: object | None = None


@dataclass(frozen=True, slots=True)
class LearningProposal:
    """Suggested learning change with evidence and lifecycle (FR-009..FR-013)."""

    proposal_id: UUID
    profile_id: UUID
    concept_id: UUID
    concept_key: str
    policy_version_id: UUID
    policy_version: str
    change: ProposalChange
    prior_fact: Mapping[str, object] | None
    evidence_refs: tuple[Mapping[str, object], ...]
    state: ProposalState
    expires_at: datetime
    superseded_by: UUID | None
    applied_profile_version_id: UUID | None
    applied_run_id: UUID | None
    created_at: datetime
    correlation_id: UUID
    actor_kind: str = "service"
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class ConfirmationResult:
    """Outcome of confirming a learning proposal (FR-012/FR-014)."""

    proposal: LearningProposal
    applied_profile_version: int
    run_id: UUID | None


class FeedbackError(Exception):
    """Base class for sanitized feedback failures."""

    code = "feedback.error"


class FeedbackValidationError(FeedbackError):
    """An action violates the feedback or learning contracts."""

    def __init__(self, error_codes: tuple[str, ...]) -> None:
        self.error_codes = error_codes
        self.code = "feedback.validation_failed"
        super().__init__(",".join(error_codes))


class FeedbackNotFound(FeedbackError):
    """A requested profile, listing or proposal does not exist."""

    code = "feedback.not_found"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class FeedbackNotAccessible(FeedbackError):
    """The requested resource belongs to another owner."""

    code = "feedback.not_accessible"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class FeedbackStateError(FeedbackError):
    """The current decision state does not allow the requested operation."""

    code = "feedback.state_error"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class FeedbackTerminal(FeedbackStateError):
    """The listing is contacted; further feedback is not allowed."""

    code = "feedback_terminal"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class FeedbackInvalidReason(FeedbackValidationError):
    """A reason key is unknown or not allowed for the event type."""

    def __init__(self, reason_key: str) -> None:
        super().__init__((f"feedback.invalid_reason:{reason_key}",))


class FeedbackConflict(FeedbackStateError):
    """The state changed concurrently; retry with a fresh read."""

    code = "feedback_conflict"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class ProposalNotFound(FeedbackNotFound):
    """A requested learning proposal does not exist."""

    code = "proposal_not_found"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class ProposalNotPending(FeedbackStateError):
    """A proposal is not pending, so the requested transition is invalid."""

    code = "proposal_not_pending"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class ProposalExpired(FeedbackStateError):
    """A proposal has passed its expiration window."""

    code = "proposal_expired"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class ProposalNotConfirmed(FeedbackStateError):
    """Only confirmed proposals can be undone."""

    code = "proposal_not_confirmed"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


def is_event_type(value: str) -> bool:
    return value in _EVENT_TYPES


def is_polarity(value: str) -> bool:
    return value in _POLARITIES


def is_proposal_state(value: str) -> bool:
    return value in _PROPOSAL_STATES
