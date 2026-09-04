"""Pure values and errors for durable preference interpretation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from umbral.application.criteria.contracts import MatcherType
from umbral.application.preferences.intensity import (
    PreferenceIntensity,
    PreferencePolarity,
)

PreferenceAuthority = Literal["explicit", "deliberate_feedback", "passive"]
BindingKind = Literal["structured", "semantic", "unresolved", "forbidden"]
PreferenceStatus = Literal["active", "superseded", "withdrawn"]
BindingStatus = Literal["active", "superseded"]
BindingMode = Literal["soft", "hard"]
PreferenceSourceKind = Literal[
    "chat", "structured", "feedback", "suggestion", "migration"
]
PreferenceMutationKind = Literal["record", "revise", "withdraw"]

ABSOLUTE_SEMANTIC_MAX_WEIGHT = 0.10


@dataclass(frozen=True, slots=True)
class PreferenceConcept:
    """The shared capability a structured binding may reference."""

    key: str
    matcher_type: MatcherType
    computable: bool


@dataclass(frozen=True, slots=True)
class PreferencePolicySpec:
    """Validated policy values needed to interpret a preference binding."""

    authority_order: tuple[PreferenceAuthority, ...]
    semantic_mode: BindingMode
    semantic_max_weight: float
    missing_evidence_contribution: float
    policy_version: str = "preference-policy-v1"

    def __post_init__(self) -> None:
        if self.semantic_mode != "soft":
            raise ValueError("semantic_mode must be soft")
        if not 0.0 <= self.semantic_max_weight <= ABSOLUTE_SEMANTIC_MAX_WEIGHT:
            raise ValueError("semantic_max_weight exceeds absolute maximum")
        if self.missing_evidence_contribution != 0.0:
            raise ValueError("missing_evidence_contribution must be zero")

    @classmethod
    def v1(cls) -> PreferencePolicySpec:
        return cls(
            authority_order=("explicit", "deliberate_feedback", "passive"),
            semantic_mode="soft",
            semantic_max_weight=0.10,
            missing_evidence_contribution=0.0,
        )


@dataclass(frozen=True, slots=True)
class HardConfirmationRef:
    """Durable action that explicitly confirmed one structured hard binding."""

    action_id: UUID


@dataclass(frozen=True, slots=True)
class BindingDraft:
    """A proposed binding before it receives durable identity and lineage."""

    kind: BindingKind
    concept_key: str | None
    matcher_type: MatcherType | None
    mode: BindingMode
    params: Mapping[str, object]
    confidence: float
    evidence_refs: tuple[Mapping[str, object], ...] = ()
    limitations: tuple[str, ...] = ()
    query_embedding: tuple[float, ...] | None = None
    embedding_version_id: UUID | None = None
    confirmation: HardConfirmationRef | None = None

    @classmethod
    def structured(
        cls,
        *,
        concept_key: str,
        matcher_type: MatcherType,
        params: Mapping[str, object],
        confidence: float,
        mode: BindingMode = "soft",
        evidence_refs: tuple[Mapping[str, object], ...] = (),
        limitations: tuple[str, ...] = (),
        confirmation: HardConfirmationRef | None = None,
    ) -> BindingDraft:
        return cls(
            kind="structured",
            concept_key=concept_key,
            matcher_type=matcher_type,
            mode=mode,
            params=dict(params),
            confidence=confidence,
            evidence_refs=evidence_refs,
            limitations=limitations,
            confirmation=confirmation,
        )

    @classmethod
    def semantic(
        cls,
        *,
        query_embedding: tuple[float, ...],
        embedding_version_id: UUID,
        confidence: float,
        weight: float = 0.10,
        evidence_refs: tuple[Mapping[str, object], ...] = (),
        limitations: tuple[str, ...] = (),
    ) -> BindingDraft:
        return cls(
            kind="semantic",
            concept_key=None,
            matcher_type="semantic_feature",
            mode="soft",
            params={"weight": weight},
            confidence=confidence,
            evidence_refs=evidence_refs,
            limitations=limitations,
            query_embedding=query_embedding,
            embedding_version_id=embedding_version_id,
        )

    @classmethod
    def unresolved(cls, reason: str) -> BindingDraft:
        return cls(
            kind="unresolved",
            concept_key=None,
            matcher_type=None,
            mode="soft",
            params={"reason": reason},
            confidence=0.0,
            limitations=(reason,),
        )

    @classmethod
    def forbidden(cls, reason: str) -> BindingDraft:
        return cls(
            kind="forbidden",
            concept_key=None,
            matcher_type=None,
            mode="soft",
            params={"reason": reason},
            confidence=0.0,
            limitations=(reason,),
        )


@dataclass(frozen=True, slots=True)
class PreferenceExpression:
    """The complete wording a person expressed for one radar."""

    expression_id: UUID
    profile_id: UUID
    source_message_id: UUID | None
    source_kind: PreferenceSourceKind
    subject_key: str
    raw_text: str
    authority: PreferenceAuthority
    status: PreferenceStatus
    superseded_by: UUID | None
    original_text_available: bool
    created_at: datetime
    correlation_id: UUID
    actor_kind: str = "service"
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class CriterionBinding:
    """Versioned interpretation of one expression against product evidence."""

    binding_id: UUID
    expression_id: UUID
    kind: BindingKind
    concept_key: str | None
    matcher_type: MatcherType | None
    mode: BindingMode
    params: Mapping[str, object]
    confidence: float
    evidence_refs: tuple[Mapping[str, object], ...]
    limitations: tuple[str, ...]
    interpretation_version: str
    query_embedding: tuple[float, ...] | None
    embedding_version_id: UUID | None
    status: BindingStatus
    superseded_by: UUID | None
    created_at: datetime
    correlation_id: UUID
    actor_kind: str = "service"
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class BindingSupersession:
    """Explicit lineage from a retired binding to its successor, if any."""

    previous_binding_id: UUID
    replacement_binding_id: UUID | None


@dataclass(frozen=True, slots=True)
class PreferenceMutation:
    """One all-or-nothing durable preference state transition."""

    kind: PreferenceMutationKind
    expression: PreferenceExpression
    bindings: tuple[CriterionBinding, ...]
    fact_binding_ids: tuple[UUID, ...]
    previous_expression_id: UUID | None = None
    binding_supersessions: tuple[BindingSupersession, ...] = ()


@dataclass(frozen=True, slots=True)
class PreferenceMutationResult:
    """Fact identities created inside the same mutation as their bindings."""

    fact_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class PreferenceChange:
    """One durable expression mutation and the bindings it created or retired."""

    expression: PreferenceExpression
    bindings: tuple[CriterionBinding, ...]
    fact_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class PreferenceView:
    """Inspectable active interpretation without exposing query vectors."""

    expression_id: UUID
    raw_text: str
    subject_key: str
    status: PreferenceStatus
    binding_id: UUID
    binding_kind: BindingKind
    mode: BindingMode
    confidence: float
    limitations: tuple[str, ...]
    evidence_refs: tuple[Mapping[str, object], ...]
    concept_key: str | None = None
    polarity: PreferencePolarity | None = None
    intensity: PreferenceIntensity | None = None
    weight: float | None = None
    intensity_policy_version: str | None = None


class PreferenceError(Exception):
    """Base class for sanitized preference failures."""

    code = "preferences.error"


class PreferenceValidationError(PreferenceError):
    """A proposed expression or binding violates deterministic policy."""

    code = "preferences.validation_failed"

    def __init__(self, error_codes: tuple[str, ...]) -> None:
        self.error_codes = error_codes
        super().__init__(",".join(error_codes))


class PreferenceAuthorityError(PreferenceError):
    """A lower-authority statement cannot replace the active expression."""

    code = "preferences.authority_insufficient"


class PreferenceNotFound(PreferenceError):
    """A requested expression cannot be found in the selected radar."""

    code = "preferences.not_found"
