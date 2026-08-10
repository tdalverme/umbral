"""Pure compilation of preferences and edits into executable criteria."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from umbral.application.criteria.contracts import (
    CompiledCriterion,
    CriteriaValidationError,
    MatcherType,
    PreferenceFact,
    SoftToHardRequiresConfirmation,
)
from umbral.application.criteria.registry import (
    ConceptLike,
    ConceptsSeedSpec,
    MatcherTypesSpec,
    is_computable,
    resolve_alias,
)

_SEMANTIC_MEMORY_REF = "edit:memory"


@dataclass(frozen=True, slots=True)
class CompilationDraft:
    """Ordered criteria plus warnings and recorded confirmations."""

    criteria: tuple[CompiledCriterion, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    confirmations: tuple[str, ...] = field(default_factory=tuple)


def compile_criteria(
    *,
    concepts: Mapping[str, ConceptLike],
    matcher_types: MatcherTypesSpec,
    facts: tuple[PreferenceFact, ...],
    edits: tuple[Mapping[str, object], ...],
    confirmations: tuple[str, ...] = (),
) -> CompilationDraft:
    """Compile ordered, versioned criteria with explicit warnings.

    Semantic memory is never compiled: an edit whose ``source_ref`` starts with
    ``edit:memory`` produces a warning and is skipped. A soft->hard conversion
    without a recorded confirmation raises
    ``SoftToHardRequiresConfirmation`` and never converts silently.
    """

    by_key = _concept_map(concepts)
    compiled: list[CompiledCriterion] = []
    warnings: list[str] = []

    for raw in edits:
        if not isinstance(raw, Mapping):
            warnings.append("criteria.edit_invalid_shape")
            continue
        concept_key = _required(raw, "concept_key")
        source_ref = str(raw.get("source_ref", ""))
        if source_ref.startswith(_SEMANTIC_MEMORY_REF):
            warnings.append("semantic_memory_needs_explicit_edit")
            continue
        concept = _lookup_concept(by_key, concept_key)
        if concept is None:
            raise _validation("criteria.concept_not_found", concept_key)
        if not is_computable(_compute_policy(concept)):
            raise _validation("criteria.concept_not_computable", concept_key)
        matcher_type = str(raw.get("matcher_type", ""))
        if matcher_type != concept.matcher_type:
            raise _validation(
                "criteria.matcher_type_mismatch", concept_key, matcher_type
            )
        params = raw.get("params")
        if not isinstance(params, Mapping):
            raise _validation("criteria.params_invalid", concept_key)
        spec = matcher_types.matcher_types.get(cast(MatcherType, matcher_type))
        allowed = spec.allowed_params if spec is not None else ()
        invalid_params = [key for key in params if key not in allowed]
        if invalid_params:
            raise _validation(
                "criteria.invalid_param",
                concept_key,
                ",".join(sorted(invalid_params)),
            )
        soft_to_hard = bool(raw.get("soft_to_hard", False))
        if soft_to_hard and concept_key not in confirmations:
            raise SoftToHardRequiresConfirmation(concept_key)
        compiled.append(
            CompiledCriterion(
                concept_key=concept_key,
                matcher_type=matcher_type,  # type: ignore[arg-type]
                params=dict(params),
                source_ref=source_ref,
                soft_to_hard=soft_to_hard,
            )
        )

    fact_criteria = _facts_to_criteria(by_key, facts, warnings)
    compiled.extend(fact_criteria)
    return CompilationDraft(
        criteria=tuple(compiled),
        warnings=tuple(warnings),
        confirmations=tuple(confirmations),
    )


def _facts_to_criteria(
    by_key: Mapping[str, ConceptLike],
    facts: tuple[PreferenceFact, ...],
    warnings: list[str],
) -> list[CompiledCriterion]:
    ordered = sorted(
        facts,
        key=lambda fact: (-fact.weight, fact.created_at, str(fact.fact_id)),
    )
    criteria: list[CompiledCriterion] = []
    for fact in ordered:
        concept = _lookup_concept(by_key, fact.concept_key)
        if concept is None:
            warnings.append(f"fact_concept_not_found:{fact.concept_key}")
            continue
        criteria.append(
            CompiledCriterion(
                concept_key=fact.concept_key,
                matcher_type=cast(MatcherType, concept.matcher_type),
                params=dict(concept.params_schema),
                source_ref=f"fact:{fact.fact_id}",
                soft_to_hard=False,
            )
        )
    return criteria


def _concept_map(concepts: Mapping[str, ConceptLike]) -> Mapping[str, ConceptLike]:
    if isinstance(concepts, ConceptsSeedSpec):
        return {
            concept.key: cast(ConceptLike, concept) for concept in concepts.concepts
        }
    return concepts


def _compute_policy(concept: ConceptLike) -> Mapping[str, object]:
    return dict(concept.compute_policy)


def _lookup_concept(
    by_key: Mapping[str, ConceptLike], concept_key: str
) -> ConceptLike | None:
    concept = by_key.get(concept_key)
    if concept is not None:
        return concept
    resolved = resolve_alias({str(k): v for k, v in by_key.items()}, concept_key)
    return by_key.get(resolved) if resolved is not None else None


def _required(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise CriteriaValidationError(("criteria.edit_invalid",))
    return value


def _validation(*parts: object) -> CriteriaValidationError:
    return CriteriaValidationError(tuple(str(part) for part in parts))
