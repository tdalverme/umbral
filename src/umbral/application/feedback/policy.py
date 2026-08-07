"""Pure parsing and validation of the versioned learning policy (FR-009).

The policy document is versioned and immutable once persisted. Validation
rejects thresholds that are not coherent without persisting partial data.
"""

from __future__ import annotations

from collections.abc import Mapping

from umbral.application.feedback.contracts import (
    FeedbackValidationError,
    LearningPolicyDoc,
)


def parse_learning_policy(data: Mapping[str, object]) -> LearningPolicyDoc:
    """Parse and validate a learning policy document; raises on errors."""

    errors: list[str] = []
    if data.get("contract_version") != "1":
        errors.append("learning_policy.unsupported_contract_version")
    version = data.get("learning_policy_version")
    if not isinstance(version, str) or not version:
        errors.append("learning_policy.version_required")

    min_signals = _int(data.get("min_signals"), 0)
    if min_signals < 1:
        errors.append("learning_policy.min_signals")
    window_days = _int(data.get("window_days"), 0)
    if window_days < 1:
        errors.append("learning_policy.window_days")
    min_signal_confidence = _float(data.get("min_signal_confidence"), 0.0)
    if not 0.0 <= min_signal_confidence <= 1.0:
        errors.append("learning_policy.signal_confidence")
    cooldown_days = _int(data.get("cooldown_days"), -1)
    if cooldown_days < 0:
        errors.append("learning_policy.cooldown_days")
    expiration_days = _int(data.get("proposal_expiration_days"), 0)
    if expiration_days < 1:
        errors.append("learning_policy.expiration_days")
    suggested_weight = _float(data.get("default_suggested_weight"), 1.5)
    if not 0.0 <= suggested_weight <= 1.0:
        errors.append("learning_policy.suggested_weight")
    suggested_confidence = _float(data.get("default_suggested_confidence"), 1.5)
    if not 0.0 <= suggested_confidence <= 1.0:
        errors.append("learning_policy.suggested_confidence")

    if errors:
        raise FeedbackValidationError(tuple(errors))
    return LearningPolicyDoc(
        contract_version=str(data["contract_version"]),
        learning_policy_version=str(version),
        min_signals=min_signals,
        window_days=window_days,
        min_signal_confidence=min_signal_confidence,
        cooldown_days=cooldown_days,
        proposal_expiration_days=expiration_days,
        default_suggested_weight=suggested_weight,
        default_suggested_confidence=suggested_confidence,
    )


def _float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default
