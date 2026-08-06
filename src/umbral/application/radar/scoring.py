"""Pure deterministic baseline scoring over candidates.

Rules are loaded from ``contracts/scoring/v1/scoring-baseline.json`` and passed
in as a :class:`ScoringBaselineSpec`. The same inputs always produce the same
score and the same stable order (tie-break: score desc, total_cost asc,
listing_id asc). Contributions per dimension are returned for the match
detail; the cards show only the total score.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from umbral.application.radar.contracts import SearchProfile
from umbral.application.silver.contracts import GeoPrecision

_PRECISION_FIT = ("exact", "block", "neighborhood", "approximate", "unknown")


@dataclass(frozen=True, slots=True)
class ScoringBaselineSpec:
    contract_version: str
    score_policy_version: str
    weights: Mapping[str, float]
    rooms_fit: Mapping[str, float]
    surface_fit: Mapping[str, float]
    location_precision_fit: Mapping[str, float]
    tie_break: tuple[str, ...]
    score_round: int


def parse_scoring_baseline(data: Mapping[str, object]) -> ScoringBaselineSpec:
    if data.get("contract_version") != "1":
        raise ValueError("unsupported scoring baseline document version")
    score_policy_version = data.get("score_policy_version")
    if not isinstance(score_policy_version, str) or not score_policy_version:
        raise ValueError("score_policy_version is required")
    raw_weights = data.get("weights")
    if not isinstance(raw_weights, Mapping):
        raise ValueError("scoring weights are required")
    weights = {str(name): float(value) for name, value in raw_weights.items()}
    raw_tie = data.get("tie_break")
    tie_break = (
        tuple(str(item) for item in raw_tie) if isinstance(raw_tie, list) else ()
    )
    score_round = _as_int(data.get("score_round"), 4)
    return ScoringBaselineSpec(
        contract_version=str(data["contract_version"]),
        score_policy_version=score_policy_version,
        weights=weights,
        rooms_fit=_float_mapping(data.get("rooms_fit")),
        surface_fit=_float_mapping(data.get("surface_fit")),
        location_precision_fit=_float_mapping(data.get("location_precision_fit")),
        tie_break=tie_break,
        score_round=score_round,
    )


class ScorableListing(Protocol):
    """The minimal listing surface the scoring consumes."""

    @property
    def listing_id(self) -> UUID: ...

    @property
    def total_cost(self) -> float: ...

    @property
    def rooms(self) -> int | None: ...

    @property
    def surface_m2(self) -> float | None: ...

    @property
    def geo_precision(self) -> GeoPrecision: ...


def compute_score(
    profile: SearchProfile, listing: ScorableListing, spec: ScoringBaselineSpec
) -> tuple[float, Mapping[str, float]]:
    """Return (total score, per-dimension contributions) for one candidate."""
    budget_fit = _budget_fit(profile.budget_max, listing.total_cost)
    rooms_fit = _rooms_fit(profile.min_rooms, listing.rooms, spec)
    surface_fit = _surface_fit(
        profile.surface_min, profile.surface_max, listing.surface_m2, spec
    )
    location_fit = _location_fit(listing.geo_precision, spec)

    contributions: dict[str, float] = {
        "budget": budget_fit,
        "rooms": rooms_fit,
        "surface": surface_fit,
        "location_precision": location_fit,
    }
    score = sum(
        spec.weights.get(name, 0.0) * value for name, value in contributions.items()
    )
    return round(score, spec.score_round), contributions


def sort_key(spec: ScoringBaselineSpec) -> tuple[str, ...]:
    return spec.tie_break


def _budget_fit(budget_max: float, total_cost: float) -> float:
    if budget_max <= 0 or total_cost is None:
        return 0.0
    ratio = (budget_max - total_cost) / budget_max
    return max(0.0, min(1.0, ratio))


def _rooms_fit(min_rooms: int, rooms: int | None, spec: ScoringBaselineSpec) -> float:
    if min_rooms == 0:
        return spec.rooms_fit.get("no_min", 1.0)
    if rooms is None:
        return spec.rooms_fit.get("unknown", 0.5)
    if rooms == min_rooms:
        return spec.rooms_fit.get("equal_min", 1.0)
    return spec.rooms_fit.get("above_min", 0.85)


def _surface_fit(
    surface_min: float | None,
    surface_max: float | None,
    surface_m2: float | None,
    spec: ScoringBaselineSpec,
) -> float:
    if surface_min is None and surface_max is None:
        return spec.surface_fit.get("no_bounds", 1.0)
    if surface_m2 is None:
        return spec.surface_fit.get("unknown", 0.5)
    if surface_min is not None and surface_m2 < surface_min:
        return 0.5
    if surface_max is None:
        return spec.surface_fit.get("within", 1.0)
    if surface_m2 <= surface_max:
        return spec.surface_fit.get("within", 1.0)
    if surface_m2 <= surface_max * 1.5:
        return spec.surface_fit.get("above_max_until_1_5x", 0.8)
    return spec.surface_fit.get("above_1_5x", 0.6)


def _location_fit(geo_precision: str, spec: ScoringBaselineSpec) -> float:
    if geo_precision not in _PRECISION_FIT:
        return spec.location_precision_fit.get("unknown", 0.5)
    return spec.location_precision_fit.get(geo_precision, 0.5)


def _float_mapping(value: object) -> Mapping[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError("scoring fit table must be an object")
    return {str(name): float(item) for name, item in value.items()}


def _as_int(value: object, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default
