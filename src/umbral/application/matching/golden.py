"""Pure parsing and validation of the golden dataset contract.

The dataset is a versioned, immutable, product-reviewed contract file
(``contracts/matching/v1/golden-dataset-v1.json``). Validation rejects malformed
cases, unknown tags, unknown hard-filter outcomes, ids that do not resolve and
missing coverage, without touching any infrastructure (research R-01).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from umbral.application.matching.contracts import (
    CaseTag,
    GoldenCase,
    GoldenCriterion,
    GoldenDataset,
    GoldenListing,
    GoldenObservation,
    GoldenProfile,
    HardFilterOutcome,
    MatchingValidationError,
)

_REQUIRED_CASE_TAGS: frozenset[str] = frozenset(
    {
        "hard_filter_violation",
        "unknown",
        "subjective_preference",
        "price_boundary",
        "legacy_no_breakdown",
    }
)
_KNOWN_TAGS: frozenset[str] = _REQUIRED_CASE_TAGS
_KNOWN_HARD_FILTERS: frozenset[str] = frozenset(
    HardFilterOutcome.__args__  # type: ignore[attr-defined]
)
_KNOWN_PRECISION: frozenset[str] = frozenset(
    {"exact", "block", "neighborhood", "approximate", "unknown"}
)
_KNOWN_MATCHER_TYPES: frozenset[str] = frozenset(
    {"numeric_range", "categorical", "geo_proximity", "semantic_feature"}
)


def load_golden_dataset(path: Path) -> GoldenDataset:
    """Load and validate the golden dataset contract from a file path."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise MatchingValidationError(("matching.dataset_required",))
    return parse_golden_dataset(raw)


def parse_golden_dataset(
    data: Mapping[str, object],
    *,
    require_coverage: bool = True,
) -> GoldenDataset:
    """Parse and validate a golden dataset document; raises on the first group."""
    errors: list[str] = []
    if data.get("contract_version") != "1":
        errors.append("matching.unsupported_contract_version")
    registry_version = data.get("registry_version")
    if registry_version != "golden-dataset-v1":
        errors.append("matching.registry_version_required")
    reviewed_by = _required_str(data.get("reviewed_by"), errors, "reviewed_by")
    reviewed_at = _required_str(data.get("reviewed_at"), errors, "reviewed_at")
    baseline = _required_str(
        data.get("baseline_score_policy_version"),
        errors,
        "baseline_score_policy_version",
    )
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        errors.append("matching.cases_required")
        raw_cases = []
    cases: list[GoldenCase] = []
    seen_ids: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, Mapping):
            errors.append("matching.case_invalid_shape")
            continue
        case, case_errors = _parse_case(raw)
        if case_errors:
            errors.extend(case_errors)
            continue
        if case.id in seen_ids:
            errors.append(f"matching.duplicate_case:{case.id}")
        seen_ids.add(case.id)
        cases.append(case)
    if errors:
        raise MatchingValidationError(tuple(sorted(set(errors))))
    coverage = _coverage_tags(tuple(cases))
    missing = _REQUIRED_CASE_TAGS - coverage
    if require_coverage and missing:
        raise MatchingValidationError(
            tuple(sorted(f"matching.missing_coverage:{tag}" for tag in missing))
        )
    return GoldenDataset(
        contract_version="1",
        registry_version=str(registry_version or "golden-dataset-v1"),
        reviewed_by=reviewed_by or "",
        reviewed_at=reviewed_at or "",
        baseline_score_policy_version=baseline or "",
        cases=tuple(cases),
    )


def _parse_case(raw: Mapping[str, object]) -> tuple[GoldenCase, list[str]]:
    errors: list[str] = []
    case_id = _required_str(raw.get("id"), errors, "id")
    tags = _parse_tags(raw.get("tags"), errors)
    raw_profile = raw.get("profile")
    if not isinstance(raw_profile, Mapping):
        errors.append("matching.profile_required")
        profile = _empty_profile()
    else:
        profile, profile_errors = _parse_profile(raw_profile)
        errors.extend(profile_errors)
    raw_criteria = raw.get("criteria")
    if not isinstance(raw_criteria, list):
        raw_criteria = []
    criteria, criteria_errors = _parse_criteria(raw_criteria)
    errors.extend(criteria_errors)
    raw_listings = raw.get("listings")
    if not isinstance(raw_listings, list) or not raw_listings:
        errors.append("matching.listings_required")
        raw_listings = []
    listings, listing_ids, listing_errors = _parse_listings(raw_listings)
    errors.extend(listing_errors)
    raw_ranking = raw.get("expected_ranking")
    if not isinstance(raw_ranking, list) or not raw_ranking:
        errors.append("matching.expected_ranking_required")
        ranking: tuple[str, ...] = ()
    else:
        ranking = tuple(str(item) for item in raw_ranking)
    raw_filter = raw.get("expected_hard_filter")
    if not isinstance(raw_filter, Mapping):
        errors.append("matching.expected_hard_filter_required")
        hard_filter: Mapping[str, HardFilterOutcome] = {}
    else:
        hard_filter, filter_errors = _parse_hard_filter(raw_filter)
        errors.extend(filter_errors)
    for listing_id in ranking:
        if listing_id not in listing_ids:
            errors.append(f"matching.unknown_ranking_id:{listing_id}")
    notes = raw.get("notes")
    if notes is not None and not isinstance(notes, str):
        errors.append("matching.notes_invalid")
    return (
        GoldenCase(
            id=case_id,
            tags=tags,
            profile=profile,
            criteria=criteria,
            listings=listings,
            expected_ranking=ranking,
            expected_hard_filter=hard_filter,
            notes=str(notes) if isinstance(notes, str) else None,
        ),
        errors,
    )


def _parse_tags(raw: object, errors: list[str]) -> tuple[CaseTag, ...]:
    if not isinstance(raw, list) or not raw:
        errors.append("matching.tags_required")
        return ()
    tags: list[CaseTag] = []
    for item in raw:
        if not isinstance(item, str) or item not in _KNOWN_TAGS:
            errors.append(f"matching.unknown_tag:{item}")
            continue
        tags.append(item)  # type: ignore[arg-type]
    if len(set(tags)) != len(tags):
        errors.append("matching.duplicate_tag")
    return tuple(tags)


def _parse_profile(raw: Mapping[str, object]) -> tuple[GoldenProfile, list[str]]:
    errors: list[str] = []
    raw_zones = raw.get("zones")
    zones = (
        tuple(str(item) for item in raw_zones)
        if isinstance(raw_zones, list) and raw_zones
        else ()
    )
    if not zones:
        errors.append("matching.zones_required")
    budget_max = _as_float(raw.get("budget_max"), None)
    if budget_max is None or budget_max <= 0:
        errors.append("matching.budget_max_required")
    min_rooms = _as_int(raw.get("min_rooms"), None)
    if min_rooms is None or min_rooms < 0:
        errors.append("matching.min_rooms_required")
    surface_min = _as_float(raw.get("surface_min"), None)
    surface_max = _as_float(raw.get("surface_max"), None)
    if (
        surface_min is not None
        and surface_max is not None
        and surface_min > surface_max
    ):
        errors.append("matching.surface_range")
    return (
        GoldenProfile(
            zones=zones,
            budget_max=budget_max or 0.0,
            budget_min=_as_float(raw.get("budget_min"), None),
            min_rooms=min_rooms or 0,
            surface_min=surface_min,
            surface_max=surface_max,
        ),
        errors,
    )


def _parse_criteria(
    raw: list[object],
) -> tuple[tuple[GoldenCriterion, ...], list[str]]:
    errors: list[str] = []
    criteria: list[GoldenCriterion] = []
    for item in raw:
        if not isinstance(item, Mapping):
            errors.append("matching.criterion_invalid_shape")
            continue
        concept_key = _required_str(item.get("concept_key"), errors, "concept_key")
        matcher_type = item.get("matcher_type")
        if (
            not isinstance(matcher_type, str)
            or matcher_type not in _KNOWN_MATCHER_TYPES
        ):
            errors.append(f"matching.unsupported_matcher_type:{matcher_type}")
        params = item.get("params")
        if not isinstance(params, Mapping):
            errors.append(f"matching.params_invalid:{concept_key}")
            params = {}
        criteria.append(
            GoldenCriterion(
                concept_key=concept_key,
                matcher_type=str(matcher_type),
                params=dict(params),
            )
        )
    return tuple(criteria), errors


def _parse_listings(
    raw: list[object],
) -> tuple[tuple[GoldenListing, ...], set[str], list[str]]:
    errors: list[str] = []
    listings: list[GoldenListing] = []
    ids: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            errors.append("matching.listing_invalid_shape")
            continue
        listing_id = _required_str(item.get("listing_id"), errors, "listing_id")
        if listing_id in ids:
            errors.append(f"matching.duplicate_listing:{listing_id}")
        ids.add(listing_id)
        total_cost = _as_float(item.get("total_cost"), None)
        if total_cost is None or total_cost < 0:
            errors.append(f"matching.total_cost_invalid:{listing_id}")
        rooms = _as_int(item.get("rooms"), None)
        surface_m2 = _as_float(item.get("surface_m2"), None)
        neighborhood = item.get("neighborhood")
        if neighborhood is not None and not isinstance(neighborhood, str):
            errors.append(f"matching.neighborhood_invalid:{listing_id}")
        geo_precision = item.get("geo_precision")
        if geo_precision not in _KNOWN_PRECISION:
            errors.append(f"matching.geo_precision_invalid:{listing_id}")
        observations: list[GoldenObservation] = []
        raw_obs = item.get("observations")
        if isinstance(raw_obs, Mapping):
            for concept_key, value in raw_obs.items():
                if not isinstance(value, Mapping):
                    errors.append(
                        f"matching.observation_invalid:{listing_id}:{concept_key}"
                    )
                    continue
                observations.append(
                    GoldenObservation(
                        concept_key=str(concept_key),
                        value=value.get("value"),
                        score=_as_float(value.get("score"), 0.0) or 0.0,
                        confidence=_as_float(value.get("confidence"), 0.0) or 0.0,
                    )
                )
        elif raw_obs is not None:
            errors.append(f"matching.observations_invalid:{listing_id}")
        listings.append(
            GoldenListing(
                listing_id=listing_id,
                total_cost=total_cost or 0.0,
                rooms=rooms,
                surface_m2=surface_m2,
                neighborhood=str(neighborhood) if neighborhood is not None else None,
                geo_precision=str(geo_precision or "unknown"),
                legacy=bool(item.get("legacy", False)),
                observations=tuple(observations),
            )
        )
    return tuple(listings), ids, errors


def _parse_hard_filter(
    raw: Mapping[str, object],
) -> tuple[Mapping[str, HardFilterOutcome], list[str]]:
    errors: list[str] = []
    result: dict[str, HardFilterOutcome] = {}
    for listing_id, value in raw.items():
        if not isinstance(value, str) or value not in _KNOWN_HARD_FILTERS:
            errors.append(f"matching.unknown_hard_filter:{listing_id}:{value}")
            continue
        result[str(listing_id)] = cast(HardFilterOutcome, value)
    return result, errors


def _coverage_tags(cases: tuple[GoldenCase, ...]) -> frozenset[str]:
    covered: set[str] = set()
    for case in cases:
        covered.update(case.tags)
    return frozenset(covered)


def _empty_profile() -> GoldenProfile:
    return GoldenProfile(
        zones=(),
        budget_max=0.0,
        budget_min=None,
        min_rooms=0,
        surface_min=None,
        surface_max=None,
    )


def _required_str(value: object, errors: list[str], field: str) -> str:
    if not isinstance(value, str) or not value:
        errors.append(f"matching.{field}_required")
        return ""
    return value


def _as_float(value: object, default: float | None) -> float | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _as_int(value: object, default: int | None) -> int | None:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return default
