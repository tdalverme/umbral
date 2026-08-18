"""Pure generic evaluators with one shared output contract.

Each evaluator returns ``EvaluationResult(score, confidence, state,
reason_code)``. ``unknown`` is a first-class state: missing data lowers
confidence and never counts as a mismatch (FR-006).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from umbral.application.scoring.contracts import EvaluationState
from umbral.application.scoring.policy import PolicyCriterion

_PRECISION_CONFIDENCE = {
    "exact": 1.0,
    "block": 0.95,
    "neighborhood": 0.9,
    "approximate": 0.7,
    "unknown": 0.5,
}

_PRECISION_FIT = {
    "exact": 1.0,
    "block": 0.95,
    "neighborhood": 0.9,
    "approximate": 0.7,
    "unknown": 0.5,
}


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Shared output contract of every evaluator."""

    score: float
    confidence: float
    state: EvaluationState
    reason_code: str


def evaluate_numeric_range(
    value: object, params: Mapping[str, object]
) -> EvaluationResult:
    minimum = _as_float(params.get("min"), None)
    maximum = _as_float(params.get("max"), None)
    number = _as_float(value, None)
    if number is None:
        return EvaluationResult(0.0, 0.0, "unknown", "no_observation_data")
    if minimum is not None and number < minimum:
        return EvaluationResult(0.0, 1.0, "mismatch", "concept_missing")
    if maximum is not None and number > maximum:
        return EvaluationResult(0.7, 1.0, "match", "concept_observed")
    return EvaluationResult(1.0, 1.0, "match", "concept_observed")


def evaluate_categorical(
    value: object, params: Mapping[str, object]
) -> EvaluationResult:
    if value is None:
        return EvaluationResult(0.0, 0.0, "unknown", "no_observation_data")
    allowed = params.get("allowed_values")
    allowed_values = allowed if isinstance(allowed, list) else []
    polarity = str(params.get("polarity", "positive"))
    preferred = params.get("preferred_value")
    if preferred is not None:
        matched = value == preferred if polarity == "positive" else value != preferred
    elif polarity == "negative":
        # Binary domains ("true"/"false"): a negative preference matches the
        # absence marker; multi-value domains without a preferred value can
        # never match a generic negative preference.
        matched = value == "false"
    else:
        matched = value in allowed_values
    if matched:
        return EvaluationResult(1.0, 1.0, "match", "concept_observed")
    return EvaluationResult(0.0, 1.0, "mismatch", "concept_missing")


def evaluate_semantic_feature(
    observation_score: object,
    observation_confidence: object,
    params: Mapping[str, object],
) -> EvaluationResult:
    score = _as_float(observation_score, None)
    if score is None:
        return EvaluationResult(0.0, 0.0, "unknown", "no_observation_data")
    threshold = _as_float(params.get("threshold"), 0.5) or 0.5
    confidence = _as_float(observation_confidence, score)
    polarity = str(params.get("polarity", "positive"))
    if polarity == "negative":
        # "no me gusta la luminosidad": a low observed score is the match and
        # the contribution grows as the observed score drops (1 - score).
        degree = round(1.0 - score, 4)
        state: EvaluationState = "match" if degree >= threshold else "mismatch"
    else:
        degree = round(score, 4)
        state = "match" if degree >= threshold else "mismatch"
    reason = "concept_observed" if state == "match" else "concept_missing"
    return EvaluationResult(degree, confidence or 0.0, state, reason)


def evaluate_geo_proximity(in_zone: bool, geo_precision: str) -> EvaluationResult:
    confidence = _PRECISION_CONFIDENCE.get(geo_precision, 0.5)
    if in_zone:
        return EvaluationResult(1.0, confidence, "match", "location_near_preferred")
    return EvaluationResult(0.3, confidence, "mismatch", "location_outside_preferred")


def evaluate_fixed_criterion(
    key: str,
    *,
    budget_max: float,
    total_cost: float,
    min_rooms: int,
    rooms: int | None,
    surface_min: float | None,
    surface_max: float | None,
    surface_m2: float | None,
    zones: tuple[str, ...],
    neighborhood: str | None,
    geo_precision: str,
) -> EvaluationResult:
    """Evaluate one of the fixed criteria from profile and listing data."""

    if key == "presupuesto":
        if total_cost is None:
            return EvaluationResult(0.0, 0.0, "unknown", "no_observation_data")
        if budget_max <= 0:
            return EvaluationResult(1.0, 1.0, "match", "budget_within_headroom")
        if total_cost > budget_max:
            return EvaluationResult(0.0, 1.0, "mismatch", "budget_over_max")
        fit = max(0.0, min(1.0, (budget_max - total_cost) / budget_max))
        return EvaluationResult(round(fit, 4), 1.0, "match", "budget_within_headroom")
    if key == "ambientes":
        if min_rooms == 0:
            return EvaluationResult(1.0, 1.0, "match", "rooms_match")
        if rooms is None:
            return EvaluationResult(0.5, 0.0, "unknown", "no_observation_data")
        if rooms == min_rooms:
            return EvaluationResult(1.0, 1.0, "match", "rooms_match")
        return EvaluationResult(0.85, 1.0, "match", "rooms_above_min")
    if key == "superficie":
        if surface_min is None and surface_max is None:
            return EvaluationResult(1.0, 1.0, "match", "surface_within_bounds")
        if surface_m2 is None:
            return EvaluationResult(0.5, 0.0, "unknown", "no_observation_data")
        if surface_min is not None and surface_m2 < surface_min:
            return EvaluationResult(0.5, 1.0, "mismatch", "concept_missing")
        if surface_max is None:
            return EvaluationResult(1.0, 1.0, "match", "surface_within_bounds")
        if surface_m2 <= surface_max:
            return EvaluationResult(1.0, 1.0, "match", "surface_within_bounds")
        if surface_m2 <= surface_max * 1.5:
            return EvaluationResult(0.8, 1.0, "match", "surface_within_bounds")
        return EvaluationResult(0.6, 1.0, "match", "surface_within_bounds")
    if key == "ubicacion":
        in_zone = False
        if neighborhood is not None:
            normalized = neighborhood.casefold()
            in_zone = any(zone.casefold() == normalized for zone in zones)
        return evaluate_geo_proximity(in_zone, geo_precision)
    return EvaluationResult(0.0, 0.0, "unknown", "no_observation_data")


def evaluate_observation_criterion(
    criterion: PolicyCriterion,
    observation_value: object,
    observation_score: object,
    observation_confidence: object,
) -> EvaluationResult:
    """Dispatch an observation-based criterion by its matcher type."""

    if criterion.matcher_type == "numeric_range":
        return evaluate_numeric_range(observation_value, criterion.params)
    if criterion.matcher_type == "categorical":
        return evaluate_categorical(observation_value, criterion.params)
    if criterion.matcher_type == "semantic_feature":
        return evaluate_semantic_feature(
            observation_score, observation_confidence, criterion.params
        )
    if criterion.matcher_type == "signal_score":
        return _evaluate_signal_score(observation_score, observation_confidence)
    return evaluate_geo_proximity(False, "unknown")


def _evaluate_signal_score(
    observation_score: object,
    observation_confidence: object,
) -> EvaluationResult:
    """Score of a normalized urban signal flows through as-is.

    The observation already carries a normalized score (0-1) and a confidence
    derived from input coverage. Missing/unknown data stays explicitly
    unknown; a present signal is a match with its declared confidence.
    """
    score = _as_float(observation_score, None)
    if score is None:
        return EvaluationResult(0.0, 0.0, "unknown", "no_observation_data")
    confidence = _as_float(observation_confidence, 0.0) or 0.0
    return EvaluationResult(
        round(score, 4), round(confidence, 4), "match", "signal_observed"
    )


def _as_float(value: object, default: float | None) -> float | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default
