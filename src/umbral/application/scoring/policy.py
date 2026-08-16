"""Pure parsing and validation of scoring policy documents.

The policy document is versioned and immutable once persisted. Validation
rejects weights that do not normalize, unsupported matcher types or params,
unsupported gates and dangling bonus/penalty references without persisting
partial data (FR-001/FR-002).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from umbral.application.criteria.contracts import MatcherType
from umbral.application.criteria.registry import MatcherTypesSpec
from umbral.application.scoring.contracts import (
    EvaluationState,
    ScoringValidationError,
)

FIXED_CRITERIA_KEYS = frozenset({"presupuesto", "ambientes", "superficie", "ubicacion"})
_SUPPORTED_GATES = ("cap_0.6_on_mismatch", "cap_0.6_on_unknown", "exclude_on_mismatch")
_SUPPORTED_TIE_KEYS = ("score", "total_cost_asc", "listing_id_asc")
_WEIGHT_EPSILON = 1e-6


@dataclass(frozen=True, slots=True)
class PolicyCriterion:
    """One criterion entry of a scoring policy."""

    key: str
    concept: str
    matcher_type: MatcherType
    weight: float
    params: Mapping[str, object]
    gate: str | None


@dataclass(frozen=True, slots=True)
class PolicyBonusPenalty:
    """A bonus or penalty applied when a criterion reaches a state."""

    criterion: str
    state: EvaluationState
    delta: float


@dataclass(frozen=True, slots=True)
class SemanticPolicy:
    """The semantic-signal policy block of a scoring policy v2 document."""

    mode: str
    max_weight: float
    missing_evidence_contribution: float


_SEMANTIC_MAX_WEIGHT = 0.10


@dataclass(frozen=True, slots=True)
class ScoringPolicyDoc:
    """Validated, executable interpretation of one policy version payload."""

    contract_version: str
    score_policy_version: str
    normalization: str
    score_round: int
    confidence: Mapping[str, float]
    criteria: tuple[PolicyCriterion, ...]
    bonuses: tuple[PolicyBonusPenalty, ...]
    penalties: tuple[PolicyBonusPenalty, ...]
    tie_break: tuple[str, ...]
    semantic: SemanticPolicy | None = None

    @property
    def criterion_by_key(self) -> Mapping[str, PolicyCriterion]:
        return {criterion.key: criterion for criterion in self.criteria}


def parse_policy_document(
    data: Mapping[str, object], matcher_types: MatcherTypesSpec
) -> ScoringPolicyDoc:
    """Parse and validate a policy document; raises on the first error group."""

    errors: list[str] = []
    contract_version = data.get("contract_version")
    if contract_version not in {"1", "2"}:
        errors.append("policy.unsupported_contract_version")
    score_policy_version = data.get("score_policy_version")
    if not isinstance(score_policy_version, str) or not score_policy_version:
        errors.append("policy.score_policy_version_required")
    normalization = str(data.get("normalization", "weighted_sum"))
    if normalization != "weighted_sum":
        errors.append("policy.unsupported_normalization")
    score_round = _as_int(data.get("score_round"), 4)
    if not 2 <= score_round <= 6:
        errors.append("policy.invalid_score_round")
    confidence = _confidence(data.get("confidence"))
    semantic = _semantic_policy(data.get("semantic"), errors)
    raw_criteria = data.get("criteria")
    criteria: list[PolicyCriterion] = []
    if isinstance(raw_criteria, list) and raw_criteria:
        keys: set[str] = set()
        for entry in raw_criteria:
            parsed = _parse_criterion(entry, matcher_types, keys, errors)
            if parsed is not None:
                criteria.append(parsed)
        total = sum(criterion.weight for criterion in criteria)
        if abs(total - 1.0) > _WEIGHT_EPSILON:
            errors.append("policy.weights_not_normalizing")
    else:
        errors.append("policy.criteria_required")
    bonuses = _parse_deltas(
        data.get("bonuses"), criteria, "policy.unknown_criterion_reference", errors
    )
    penalties = _parse_deltas(
        data.get("penalties"), criteria, "policy.unknown_criterion_reference", errors
    )
    tie_break = _tie_break(data.get("tie_break"), errors)
    if errors:
        raise ScoringValidationError(tuple(errors))
    return ScoringPolicyDoc(
        contract_version=str(contract_version or ""),
        score_policy_version=str(score_policy_version or ""),
        normalization=normalization,
        score_round=score_round,
        confidence=confidence,
        criteria=tuple(criteria),
        bonuses=bonuses,
        penalties=penalties,
        tie_break=tie_break,
        semantic=semantic,
    )


def _semantic_policy(
    raw: object, errors: list[str]
) -> SemanticPolicy | None:
    """Parse the v2 semantic block; semantic signals are always soft-capped."""
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        errors.append("policy.semantic_invalid_shape")
        return None
    mode = raw.get("mode")
    if mode != "soft":
        errors.append("policy.semantic_must_be_soft")
    max_weight = _as_float(raw.get("max_weight"), _SEMANTIC_MAX_WEIGHT)
    if max_weight is None or max_weight > _SEMANTIC_MAX_WEIGHT:
        errors.append("policy.semantic_max_weight_exceeded")
    missing = _as_float(raw.get("missing_evidence_contribution"), 0.0)
    if missing not in (None, 0.0):
        errors.append("policy.semantic_missing_evidence_nonzero")
    return SemanticPolicy(
        mode="soft",
        max_weight=max_weight if max_weight is not None else _SEMANTIC_MAX_WEIGHT,
        missing_evidence_contribution=0.0,
    )


def is_fixed_criterion(key: str) -> bool:
    return key in FIXED_CRITERIA_KEYS


def _parse_criterion(
    raw: object,
    matcher_types: MatcherTypesSpec,
    keys: set[str],
    errors: list[str],
) -> PolicyCriterion | None:
    if not isinstance(raw, Mapping):
        errors.append("policy.criterion_invalid_shape")
        return None
    key = raw.get("key")
    if not isinstance(key, str) or not key:
        errors.append("policy.criterion_key_required")
        return None
    if key in keys:
        errors.append(f"policy.duplicate_criterion:{key}")
        return None
    keys.add(key)
    concept = raw.get("concept")
    if not isinstance(concept, str) or not concept:
        errors.append(f"policy.criterion_concept_required:{key}")
        return None
    matcher_type = raw.get("matcher_type")
    if not isinstance(matcher_type, str):
        errors.append(f"policy.unsupported_matcher_type:{key}")
        return None
    spec = matcher_types.matcher_types.get(cast(MatcherType, matcher_type))
    if spec is None:
        errors.append("policy.unsupported_matcher_type")
        return None
    params = raw.get("params")
    if not isinstance(params, Mapping):
        errors.append(f"policy.params_invalid:{key}")
        params = {}
    invalid = [name for name in params if name not in spec.allowed_params]
    if invalid:
        errors.append("policy.invalid_param")
    weight = _as_float(raw.get("weight"), None)
    if weight is None or not 0.0 <= weight <= 1.0:
        errors.append(f"policy.invalid_weight:{key}")
    gate = raw.get("gate")
    if gate is not None and gate not in _SUPPORTED_GATES:
        errors.append("policy.unsupported_gate")
    return PolicyCriterion(
        key=key,
        concept=concept,
        matcher_type=cast(MatcherType, matcher_type),
        weight=weight if weight is not None else 0.0,
        params=dict(params),
        gate=cast(str | None, gate),
    )


def _parse_deltas(
    raw: object,
    criteria: list[PolicyCriterion],
    error_code: str,
    errors: list[str],
) -> tuple[PolicyBonusPenalty, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        errors.append(error_code)
        return ()
    known = {criterion.key for criterion in criteria}
    deltas: list[PolicyBonusPenalty] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            errors.append(error_code)
            continue
        criterion = entry.get("criterion")
        state = entry.get("state")
        delta = _as_float(entry.get("delta"), None)
        if criterion not in known or state not in {"match", "mismatch", "unknown"}:
            errors.append(error_code)
            continue
        if delta is None or not -0.2 <= delta <= 0.2:
            errors.append(f"policy.invalid_delta:{criterion}")
            continue
        deltas.append(
            PolicyBonusPenalty(
                criterion=str(criterion),
                state=cast(EvaluationState, state),
                delta=delta,
            )
        )
    return tuple(deltas)


def _tie_break(raw: object, errors: list[str]) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        errors.append("policy.invalid_tie_break")
        return ()
    tie_break = tuple(str(item) for item in raw)
    if not tie_break or tie_break[0] != "score":
        errors.append("policy.invalid_tie_break")
        return ()
    unsupported = [key for key in tie_break[1:] if key not in _SUPPORTED_TIE_KEYS]
    if unsupported:
        errors.append(f"policy.invalid_tie_break:{','.join(unsupported)}")
    return tie_break


def _confidence(raw: object) -> Mapping[str, float]:
    if not isinstance(raw, Mapping):
        return {
            "unknown_penalty": 0.2,
            "strong_threshold": 0.8,
            "medium_threshold": 0.5,
        }
    return {
        "unknown_penalty": _as_float(raw.get("unknown_penalty"), 0.2) or 0.2,
        "strong_threshold": _as_float(raw.get("strong_threshold"), 0.8) or 0.8,
        "medium_threshold": _as_float(raw.get("medium_threshold"), 0.5) or 0.5,
    }


def _as_float(value: object, default: float | None) -> float | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    return default
