"""Pure parsing and validation of the quick-reasons seed (FR-006).

The seed is a versioned contract file. Unknown reason keys, polarities or
concept references are rejected at validation time so events never reference a
category that does not exist or is not allowed for the action.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from umbral.application.feedback.contracts import (
    FeedbackEventType,
    FeedbackValidationError,
    Polarity,
    QuickReason,
    QuickReasonsSpec,
    is_event_type,
    is_polarity,
)

_EVENT_TYPES = {"like", "dislike", "save", "dismiss", "contacted"}
_MAX_REASON_KEYS = 100


def parse_quick_reasons(
    data: Mapping[str, object], concept_keys: tuple[str, ...]
) -> QuickReasonsSpec:
    """Parse and validate the quick-reasons seed; raises on the first error group."""

    errors: list[str] = []
    if data.get("contract_version") != "1":
        errors.append("quick_reasons.unsupported_contract_version")
    registry_version = data.get("registry_version")
    if not isinstance(registry_version, str) or not registry_version:
        errors.append("quick_reasons.registry_version_required")
    raw_reasons = data.get("reasons")
    reasons: list[QuickReason] = []
    if isinstance(raw_reasons, list) and raw_reasons:
        keys: set[str] = set()
        for raw in raw_reasons:
            parsed = _parse_reason(raw, concept_keys, keys, errors)
            if parsed is not None:
                reasons.append(parsed)
    else:
        errors.append("quick_reasons.reasons_required")
    if errors:
        raise FeedbackValidationError(tuple(errors))
    return QuickReasonsSpec(
        registry_version=str(registry_version),
        contract_version=str(data["contract_version"]),
        reasons=tuple(reasons),
    )


def _parse_reason(
    raw: object,
    concept_keys: tuple[str, ...],
    keys: set[str],
    errors: list[str],
) -> QuickReason | None:
    if not isinstance(raw, Mapping):
        errors.append("quick_reasons.reason_invalid_shape")
        return None
    key = raw.get("key")
    if not isinstance(key, str) or not key:
        errors.append("quick_reasons.reason_key_required")
        return None
    if key in keys:
        errors.append(f"quick_reasons.duplicate_key:{key}")
        return None
    keys.add(key)
    label = raw.get("label")
    if not isinstance(label, str) or not label:
        errors.append(f"quick_reasons.label_required:{key}")
    polarity = raw.get("polarity")
    if not isinstance(polarity, str) or not is_polarity(polarity):
        errors.append("quick_reasons.invalid_polarity")
    concept_key = raw.get("concept_key")
    if concept_key is not None and concept_key not in concept_keys:
        errors.append("quick_reasons.unknown_concept")
    allowed_on = raw.get("allowed_on")
    allowed: tuple[FeedbackEventType, ...] = ()
    if not isinstance(allowed_on, list) or not allowed_on:
        errors.append("quick_reasons.allowed_on_required")
    else:
        parsed_allowed: list[FeedbackEventType] = []
        for item in allowed_on:
            if not isinstance(item, str) or not is_event_type(item):
                errors.append("quick_reasons.invalid_allowed_on")
            else:
                parsed_allowed.append(cast(FeedbackEventType, item))
        allowed = tuple(dict.fromkeys(parsed_allowed))
    if len(keys) > _MAX_REASON_KEYS:
        errors.append("quick_reasons.too_many_reasons")
    return QuickReason(
        key=key,
        label=str(label),
        polarity=cast(Polarity, polarity) if is_polarity(str(polarity)) else "neutral",
        concept_key=concept_key if isinstance(concept_key, str) else None,
        allowed_on=allowed,
    )
