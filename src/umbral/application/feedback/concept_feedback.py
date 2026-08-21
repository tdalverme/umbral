"""Pure validation of interpreted concept feedback (ADR 0003, FR-002/FR-003).

The LLM fills the structured interpretation; this module validates the
payload against the published schema (``feedback-concept-interpret-v1``) and
the active concept catalog. The domain service decides how the preference
model changes; the policy counting in ``signals.py`` never reads
strength/confidence (FR-004).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from umbral.application.feedback.contracts import (
    ConceptFeedback,
    FeedbackStrength,
    FeedbackValidationError,
    Polarity,
    is_polarity,
    is_strength,
)

_MAX_CONCEPT_FEEDBACK = 5


@dataclass(frozen=True, slots=True)
class ConceptFeedbackSpec:
    """Validated ``feedback-concept-interpret-v1`` document."""

    contract_version: str
    schema_version: str
    max_items: int


def parse_concept_feedback_contract(
    data: Mapping[str, object],
) -> ConceptFeedbackSpec:
    """Parse and validate the published interpretation schema document."""
    errors: list[str] = []
    if data.get("contract_version") != "1":
        errors.append("concept_feedback.unsupported_contract_version")
    schema_version = data.get("schema_version")
    if schema_version != "feedback-concept-interpret-v1":
        errors.append("concept_feedback.unsupported_schema_version")
    max_items = data.get("max_items")
    if (
        not isinstance(max_items, int)
        or isinstance(max_items, bool)
        or not 1 <= max_items <= 20
    ):
        errors.append("concept_feedback.invalid_max_items")
    forbidden = data.get("forbidden_keys")
    if not isinstance(forbidden, list):
        errors.append("concept_feedback.forbidden_keys_required")
    if errors:
        raise FeedbackValidationError(tuple(errors))
    return ConceptFeedbackSpec(
        contract_version=str(data["contract_version"]),
        schema_version=str(data["schema_version"]),
        max_items=cast(int, max_items),
    )


def validate_concept_feedback(
    items: Sequence[Mapping[str, object]],
    catalog: object,
    max_items: int = _MAX_CONCEPT_FEEDBACK,
) -> tuple[ConceptFeedback, ...]:
    """Validate interpreted concept feedback against catalog and ranges.

    ``catalog`` must expose ``get(concept_key)`` and ``is_computable``; only
    computable catalog concepts are accepted. Semantic concepts stay soft: the
    validated payload never carries mode/strength into the policy counting.
    """
    errors: list[str] = []
    validated: list[ConceptFeedback] = []
    seen: set[str] = set()
    for raw in items:
        if len(validated) >= max_items:
            errors.append("feedback.too_many_concept_reasons")
            break
        if not isinstance(raw, Mapping):
            errors.append("feedback.concept_reason_invalid_shape")
            continue
        concept_key = raw.get("concept_key")
        if not isinstance(concept_key, str) or not concept_key:
            errors.append("feedback.concept_reason_concept_required")
            continue
        if concept_key in seen:
            continue
        seen.add(concept_key)
        if not _concept_computable(catalog, concept_key):
            errors.append(f"feedback.unknown_concept:{concept_key}")
            continue
        polarity = raw.get("polarity")
        strength = raw.get("strength")
        confidence = raw.get("confidence")
        if (
            not isinstance(polarity, str)
            or not is_polarity(polarity)
            or polarity == "neutral"
        ):
            errors.append("feedback.concept_reason_invalid_polarity")
            continue
        if not isinstance(strength, str) or not is_strength(strength):
            errors.append("feedback.concept_reason_invalid_strength")
            continue
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            errors.append("feedback.concept_reason_invalid_confidence")
            continue
        if not 0.0 <= float(confidence) <= 1.0:
            errors.append("feedback.concept_reason_invalid_confidence")
            continue
        validated.append(
            ConceptFeedback(
                concept_key=concept_key,
                polarity=cast(Polarity, polarity),
                strength=cast(FeedbackStrength, strength),
                confidence=float(confidence),
            )
        )
    if errors:
        raise FeedbackValidationError(tuple(errors))
    return tuple(validated)


def _concept_computable(catalog: object, concept_key: str) -> bool:
    get = getattr(catalog, "get", None)
    if not callable(get):
        return False
    resolved = get(concept_key)
    if resolved is None:
        return False
    is_computable = getattr(catalog, "is_computable", None)
    if not callable(is_computable):
        return False
    return bool(is_computable(concept_key))