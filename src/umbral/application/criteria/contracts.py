"""Pure, transport-independent values and errors for criteria and observations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

MatcherType = Literal[
    "numeric_range", "categorical", "geo_proximity", "semantic_feature"
]
ObservationSource = Literal["rule", "model", "urban"]
ObservationState = Literal["active", "invalidated", "superseded", "failed"]
FactState = Literal["active", "superseded"]
ExtractionKind = Literal["rule", "prompt", "schema", "model", "embedding"]
RecomputeScopeKind = Literal["concept", "extraction", "parser", "full"]
RecomputeRunState = Literal["pending", "running", "succeeded", "failed"]


@dataclass(frozen=True, slots=True)
class Concept:
    """Current state of one curated concept."""

    concept_id: UUID
    key: str
    name: str
    aliases: tuple[str, ...]
    matcher_type: MatcherType
    params_schema: Mapping[str, object]
    source: str
    defaults: Mapping[str, object]
    compute_policy: Mapping[str, object]
    version: int
    current_version_id: UUID | None
    created_at: datetime
    updated_at: datetime
    correlation_id: UUID
    actor_kind: str = "service"
    actor_id: str | None = None

    def payload(self) -> Mapping[str, object]:
        """Immutable payload snapshot of the concept at its current version."""

        return {
            "key": self.key,
            "name": self.name,
            "aliases": list(self.aliases),
            "matcher_type": self.matcher_type,
            "params_schema": dict(self.params_schema),
            "source": self.source,
            "defaults": dict(self.defaults),
            "compute_policy": dict(self.compute_policy),
        }


@dataclass(frozen=True, slots=True)
class ConceptVersion:
    """Immutable snapshot of a concept; created on every change."""

    version_id: UUID
    concept_id: UUID
    concept_version: int
    payload: Mapping[str, object]
    created_at: datetime
    correlation_id: UUID
    actor_kind: str = "service"
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class PreferenceFact:
    """Append-only declared preference of one search profile."""

    fact_id: UUID
    profile_id: UUID
    concept_key: str
    value: object
    weight: float
    polarity: str
    confidence: float
    fact_source: str
    state: FactState
    superseded_by: UUID | None
    created_at: datetime
    correlation_id: UUID
    actor_kind: str = "service"
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class CompiledCriterion:
    """One executable criterion validated against the registry."""

    concept_key: str
    matcher_type: MatcherType
    params: Mapping[str, object]
    source_ref: str
    soft_to_hard: bool
    weight: float | None = None


@dataclass(frozen=True, slots=True)
class Compilation:
    """Ordered, versioned set of executable criteria with warnings."""

    compilation_id: UUID
    profile_id: UUID
    profile_version_id: UUID
    compilation_version: int
    criteria: tuple[CompiledCriterion, ...]
    warnings: tuple[str, ...]
    confirmations: tuple[str, ...]
    created_at: datetime
    correlation_id: UUID
    actor_kind: str = "service"
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractionVersion:
    """Immutable version of an extraction artifact (rule/prompt/schema/model)."""

    version_id: UUID
    kind: ExtractionKind
    key: str
    version: str
    payload: Mapping[str, object]
    created_at: datetime
    correlation_id: UUID
    actor_kind: str = "service"
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class ListingObservation:
    """One extracted fact of a listing, with evidence and lineage."""

    observation_id: UUID
    listing_id: UUID
    concept_key: str
    matcher_type: MatcherType
    value: object
    score: float
    confidence: float
    evidence: Mapping[str, object]
    source: ObservationSource
    extraction_version_id: UUID | None
    state: ObservationState
    failure_code: str | None
    recomputation_run_id: UUID | None
    created_at: datetime
    correlation_id: UUID
    actor_kind: str = "service"
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class RecomputeScope:
    """Scope of an extraction batch or a selective recompute."""

    kind: RecomputeScopeKind
    key: str | None

    def __post_init__(self) -> None:
        if self.kind != "full" and not self.key:
            raise ValueError("scope key is required for non-full scopes")

    @property
    def target(self) -> str:
        if self.kind == "full":
            return "full"
        return f"{self.kind}:{self.key}"

    @classmethod
    def parse(cls, raw: str) -> RecomputeScope:
        if raw == "full":
            return cls("full", None)
        kind, separator, key = raw.partition(":")
        if not separator or kind not in {"concept", "extraction", "parser"}:
            raise ValueError(f"invalid recompute scope target: {raw}")
        return cls(kind, key)  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class RecomputeRun:
    """One invalidation-recompute cycle with state, counts and cause."""

    run_id: UUID
    scope: RecomputeScope
    cause: str
    state: RecomputeRunState
    counts: Mapping[str, object]
    job_execution_id: UUID | None
    finished_at: datetime | None
    created_at: datetime
    correlation_id: UUID
    version: int = 1
    actor_kind: str = "service"
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Structured output of one model extraction call."""

    value: object
    evidence_fragment: str | None
    confidence: float
    failed: bool = False
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class RuleOutcome:
    """Deterministic rule extraction outcome with optional fragment evidence."""

    value: object
    fragment: str | None
    span: tuple[int, int] | None
    matched_on: tuple[str, ...] = field(default_factory=tuple)


class CriteriaError(Exception):
    """Base class for sanitized criteria failures."""

    code = "criteria.error"


class CriteriaValidationError(CriteriaError):
    """A registry, fact or compilation draft violates the contracts."""

    def __init__(self, error_codes: tuple[str, ...]) -> None:
        self.error_codes = error_codes
        self.code = "criteria.validation_failed"
        super().__init__(",".join(error_codes))


class CriteriaNotFound(CriteriaError):
    """A requested concept, fact or compilation does not exist."""

    code = "criteria.not_found"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class SoftToHardRequiresConfirmation(CriteriaValidationError):
    """A soft preference cannot become a hard filter without confirmation."""

    def __init__(self, concept_key: str) -> None:
        self.concept_key = concept_key
        super().__init__(
            (f"criteria.soft_to_hard_requires_confirmation:{concept_key}",)
        )


class CriteriaPermanentError(CriteriaError):
    """A terminal processing failure with an actionable code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


class CriteriaTransientError(CriteriaError):
    """A bounded, retryable failure explicitly declared by the worker."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)
