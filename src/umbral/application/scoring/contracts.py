"""Pure, transport-independent values and errors for scoring and explanations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

EvaluationState = Literal["match", "mismatch", "unknown"]
EvidenceLevel = Literal["strong", "medium", "low"]


@dataclass(frozen=True, slots=True)
class ScoringPolicy:
    """Current state of one scoring policy key."""

    policy_id: UUID
    key: str
    version: int
    current_version_id: UUID | None
    created_at: datetime
    updated_at: datetime
    correlation_id: UUID
    actor_kind: str = "service"
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class PolicyVersion:
    """Immutable version of a scoring policy document."""

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
class CriterionEvaluation:
    """Frozen per-run evaluation of one criterion against one listing."""

    evaluation_id: UUID
    run_id: UUID
    listing_id: UUID
    criterion_key: str
    criterion_version: str
    matcher_type: str
    params: Mapping[str, object]
    input_refs: tuple[Mapping[str, object], ...]
    score: float
    confidence: float
    state: EvaluationState
    contribution: float
    reason_code: str
    evidence_refs: tuple[Mapping[str, object], ...]
    created_at: datetime
    correlation_id: UUID


@dataclass(frozen=True, slots=True)
class ExplanationReason:
    """One reason with evidence level and deterministic copy."""

    criterion_key: str
    state: EvaluationState
    score: float
    confidence: float
    contribution: float
    evidence_level: EvidenceLevel
    reason_code: str
    evidence_refs: tuple[Mapping[str, object], ...]
    text: str


@dataclass(frozen=True, slots=True)
class ExplanationRisk:
    """A low-confidence or unknown evaluation surfaced as a risk."""

    criterion_key: str
    state: EvaluationState
    reason_code: str
    text: str


@dataclass(frozen=True, slots=True)
class Explanation:
    """Deterministic explanation generated from a frozen run."""

    search_profile_id: UUID
    run_id: UUID
    listing_id: UUID
    score_version: str
    score: float
    confidence: float
    reasons: tuple[ExplanationReason, ...]
    risks: tuple[ExplanationRisk, ...]
    missing_data: tuple[str, ...]
    satisfied_filters: tuple[str, ...]
    profile_snapshot: Mapping[str, object]
    feature_snapshot: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ComparisonDimension:
    """One homogeneous row of a structured comparison."""

    kind: Literal["fixed", "criterion"]
    key: str
    label: str
    concept: str | None = None


@dataclass(frozen=True, slots=True)
class ComparisonCell:
    """One cell of the comparison matrix."""

    listing_id: UUID
    dimension_key: str
    value: object
    state: EvaluationState
    missing: bool
    evidence_refs: tuple[Mapping[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class Comparison:
    """Structured comparison matrix; never invents a winner."""

    search_profile_id: UUID
    run_id: UUID
    score_version: str
    limit: int
    listings: tuple[Mapping[str, object], ...]
    dimensions: tuple[ComparisonDimension, ...]
    cells: tuple[ComparisonCell, ...]


class ScoringError(Exception):
    """Base class for sanitized scoring failures."""

    code = "scoring.error"


class ScoringValidationError(ScoringError):
    """A policy document violates the scoring contracts."""

    def __init__(self, error_codes: tuple[str, ...]) -> None:
        self.error_codes = error_codes
        self.code = "scoring.validation_failed"
        super().__init__(",".join(error_codes))


class ScoringNotFound(ScoringError):
    """A requested run, policy or listing does not exist."""

    code = "scoring.not_found"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class ScoringNotAccessible(ScoringError):
    """The requested resource belongs to another owner."""

    code = "scoring.not_accessible"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class ScoringStateError(ScoringError):
    """The run state does not allow the requested operation."""

    code = "scoring.state_error"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class ExplanationUnavailable(ScoringStateError):
    """The run was produced by a legacy policy without breakdown data."""

    code = "explanation_unavailable"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class ComparisonLimitExceeded(ScoringValidationError):
    """A comparison requests more listings than the policy allows."""

    def __init__(self, limit: int) -> None:
        super().__init__((f"comparison.limit_exceeded:{limit}",))


class ComparisonNotInRadar(ScoringNotAccessible):
    """A comparison references a listing outside the run of the radar."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)


class ComparisonDuplicateListing(ScoringValidationError):
    """A comparison repeats a listing id."""

    def __init__(self) -> None:
        super().__init__(("comparison.duplicate_listing",))
