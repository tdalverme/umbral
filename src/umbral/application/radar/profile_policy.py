"""Pure loader and validator for the published search profile contract.

The versioned rule set is loaded from ``contracts/search-profiles`` by an
infrastructure loader and passed in as a :class:`SearchProfilePolicySpec`.
Validation is deterministic and versioned; unknown-value strategies are explicit
per filter and never silently defaulted.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import cast

from umbral.application.radar.contracts import (
    ProfileVersion,
    RadarPermanentError,
    SearchProfile,
    SearchProfileState,
)

_KNOWN_STATES = ("active", "paused", "archived")
SEARCH_POLICY_SNAPSHOT_KEY = "search_profile_policy"


@dataclass(frozen=True, slots=True)
class SearchProfilePolicySpec:
    contract_version: str
    policy_version: str
    operation: tuple[str, ...]
    neighborhoods: tuple[str, ...]
    limits: Mapping[str, object]
    states: tuple[str, ...]
    transitions: Mapping[str, tuple[str, ...]]
    unknown_strategies: Mapping[str, str]
    error_codes: Mapping[str, str]


def parse_search_profile_policy(data: Mapping[str, object]) -> SearchProfilePolicySpec:
    if data.get("contract_version") not in {"1", "2"}:
        raise ValueError("unsupported search profile policy document version")
    policy_version = data.get("policy_version")
    if not isinstance(policy_version, str) or not policy_version:
        raise ValueError("policy_version is required")

    raw_operation = data.get("operation")
    operation = (
        tuple(str(item) for item in raw_operation)
        if isinstance(raw_operation, list)
        else ()
    )
    raw_zones = data.get("caba_neighborhoods")
    neighborhoods = (
        tuple(str(item) for item in raw_zones) if isinstance(raw_zones, list) else ()
    )
    raw_limits = data.get("limits")
    limits: Mapping[str, object] = {}
    if isinstance(raw_limits, Mapping):
        limits = {str(name): value for name, value in raw_limits.items()}
    raw_states = data.get("states")
    states = (
        tuple(str(item) for item in raw_states) if isinstance(raw_states, list) else ()
    )
    raw_transitions = data.get("transitions")
    transitions: dict[str, tuple[str, ...]] = {}
    if isinstance(raw_transitions, Mapping):
        transitions = {
            str(name): tuple(str(item) for item in values)
            for name, values in raw_transitions.items()
            if isinstance(values, list)
        }
    raw_strategies = data.get("unknown_strategies")
    strategies: dict[str, str] = {}
    if isinstance(raw_strategies, Mapping):
        strategies = {str(name): str(value) for name, value in raw_strategies.items()}
    raw_errors = data.get("error_codes")
    error_codes: dict[str, str] = {}
    if isinstance(raw_errors, Mapping):
        error_codes = {str(name): str(detail) for name, detail in raw_errors.items()}

    return SearchProfilePolicySpec(
        contract_version=str(data["contract_version"]),
        policy_version=policy_version,
        operation=operation,
        neighborhoods=neighborhoods,
        limits=limits,
        states=states,
        transitions=transitions,
        unknown_strategies=strategies,
        error_codes=error_codes,
    )


def validate_profile(
    payload: Mapping[str, object], spec: SearchProfilePolicySpec
) -> tuple[str, ...]:
    """Return the validation error codes of a profile draft (empty when valid)."""
    errors: list[str] = []

    name = payload.get("name")
    name_max = _limit_int(spec, "name_max_length", 80)
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > name_max:
        errors.append("radar.name_required")

    raw_zones = payload.get("zones")
    if not isinstance(raw_zones, list):
        errors.append("radar.zones_required")
    else:
        zones_min = _limit_int(spec, "zones_min", 1)
        zones_max = _limit_int(spec, "zones_max", 15)
        if len(raw_zones) < zones_min or len(raw_zones) > zones_max:
            errors.append("radar.zones_required")
        for zone in raw_zones:
            if not isinstance(zone, str) or zone not in spec.neighborhoods:
                errors.append("radar.zone_unknown")

    budget_max = payload.get("budget_max")
    if budget_max is None and spec.contract_version == "1":
        errors.append("radar.budget_required")
    elif budget_max is not None and (
        not isinstance(budget_max, (int, float))
        or isinstance(budget_max, bool)
        or budget_max <= 0
    ):
        errors.append(
            "radar.budget_range"
            if spec.contract_version == "2"
            else "radar.budget_required"
        )
    budget_min = payload.get("budget_min")
    if budget_min is not None and (
        not isinstance(budget_min, (int, float)) or isinstance(budget_min, bool)
    ):
        errors.append("radar.budget_range")
    elif budget_min is not None and budget_min < 0:
        errors.append("radar.budget_range")
    elif (
        budget_min is not None
        and isinstance(budget_max, (int, float))
        and budget_min >= budget_max
    ):
        errors.append("radar.budget_range")

    min_rooms = payload.get("min_rooms")
    if min_rooms is None and spec.contract_version == "2":
        pass
    elif not isinstance(min_rooms, int) or isinstance(min_rooms, bool):
        errors.append("radar.rooms_range")
    else:
        rooms_min = _limit_int(spec, "min_rooms_min", 0)
        rooms_max = _limit_int(spec, "min_rooms_max", 200)
        if min_rooms < rooms_min or min_rooms > rooms_max:
            errors.append("radar.rooms_range")

    surface_min = payload.get("surface_min")
    surface_max = payload.get("surface_max")
    surface_min_number = (
        surface_min
        if isinstance(surface_min, (int, float)) and not isinstance(surface_min, bool)
        else None
    )
    surface_max_number = (
        surface_max
        if isinstance(surface_max, (int, float)) and not isinstance(surface_max, bool)
        else None
    )
    if surface_min is not None and surface_min_number is None:
        errors.append("radar.surface_range")
    if surface_max is not None and surface_max_number is None:
        errors.append("radar.surface_range")
    if (
        surface_min_number is not None
        and surface_max_number is not None
        and surface_max_number <= surface_min_number
    ):
        errors.append("radar.surface_range")

    status = payload.get("status", "active")
    if status not in spec.states:
        errors.append("radar.state_unknown")

    return tuple(dict.fromkeys(errors))


def default_unknown_strategy(spec: SearchProfilePolicySpec) -> Mapping[str, str]:
    """The versioned per-filter unknown-value strategy of the contract."""
    return dict(spec.unknown_strategies)


def freeze_search_profile_policy(
    spec: SearchProfilePolicySpec,
    residential_property_types: frozenset[str],
) -> Mapping[str, object]:
    """Serialize the exact executable search-policy revision into a snapshot."""

    return {
        "contract_version": spec.contract_version,
        "policy_version": spec.policy_version,
        "operation": list(spec.operation),
        "caba_neighborhoods": list(spec.neighborhoods),
        "limits": dict(spec.limits),
        "states": list(spec.states),
        "transitions": {
            name: list(targets) for name, targets in spec.transitions.items()
        },
        "unknown_strategies": dict(spec.unknown_strategies),
        "error_codes": dict(spec.error_codes),
        "residential_property_types": sorted(residential_property_types),
    }


def frozen_search_profile_policy(
    version: ProfileVersion,
) -> tuple[SearchProfilePolicySpec, tuple[str, ...]]:
    raw_policy = version.payload.get(SEARCH_POLICY_SNAPSHOT_KEY)
    if not isinstance(raw_policy, Mapping):
        raise RadarPermanentError(
            "radar.search_policy_snapshot_missing",
            "profile version has no executable search policy snapshot",
        )
    required_lists = ("operation", "caba_neighborhoods", "states")
    required_mappings = (
        "limits",
        "transitions",
        "unknown_strategies",
        "error_codes",
    )
    if any(
        not isinstance(raw_policy.get(name), list) for name in required_lists
    ) or any(
        not isinstance(raw_policy.get(name), Mapping)
        for name in required_mappings
    ):
        raise RadarPermanentError(
            "radar.search_policy_snapshot_invalid",
            "profile version search policy snapshot is invalid",
        )
    raw_property_types = raw_policy.get("residential_property_types")
    if (
        not isinstance(raw_property_types, list)
        or not raw_property_types
        or any(not isinstance(item, str) or not item for item in raw_property_types)
    ):
        raise RadarPermanentError(
            "radar.search_policy_snapshot_invalid",
            "profile version search policy snapshot is invalid",
        )
    try:
        policy = parse_search_profile_policy(raw_policy)
    except ValueError as error:
        raise RadarPermanentError(
            "radar.search_policy_snapshot_invalid",
            "profile version search policy snapshot is invalid",
        ) from error
    if (
        "rental" not in policy.operation
        or not policy.neighborhoods
        or not policy.states
        or not policy.unknown_strategies
    ):
        raise RadarPermanentError(
            "radar.search_policy_snapshot_invalid",
            "profile version search policy snapshot is invalid",
        )
    return policy, tuple(raw_property_types)


def rehydrate_profile_version(
    profile: SearchProfile,
    version: ProfileVersion,
    policy: SearchProfilePolicySpec,
) -> SearchProfile:
    """Validate and restore the immutable profile inputs used by one run."""

    if version.profile_id != profile.profile_id:
        raise RadarPermanentError(
            "radar.version_profile_mismatch",
            "profile version does not belong to the recommendation run profile",
        )
    errors = validate_profile(version.payload, policy)
    raw_strategy = version.payload.get("unknown_strategy")
    if errors or version.payload.get("operation") != "rental" or not isinstance(
        raw_strategy, Mapping
    ):
        raise RadarPermanentError(
            "radar.version_payload_invalid",
            "profile version payload is invalid",
        )
    if any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in raw_strategy.items()
    ):
        raise RadarPermanentError(
            "radar.version_payload_invalid",
            "profile version payload is invalid",
        )
    raw_zones = version.payload["zones"]
    if not isinstance(raw_zones, list):
        raise RadarPermanentError(
            "radar.version_payload_invalid",
            "profile version payload is invalid",
        )
    return replace(
        profile,
        name=cast(str, version.payload["name"]),
        operation="rental",
        zones=tuple(cast(list[str], raw_zones)),
        budget_max=_optional_number(version.payload.get("budget_max")),
        budget_min=_optional_number(version.payload.get("budget_min")),
        min_rooms=_optional_int(version.payload.get("min_rooms")),
        surface_min=_optional_number(version.payload.get("surface_min")),
        surface_max=_optional_number(version.payload.get("surface_max")),
        status=cast(SearchProfileState, version.payload.get("status", "active")),
        unknown_strategy=dict(raw_strategy),
        current_version_id=version.version_id,
    )


def can_transition(spec: SearchProfilePolicySpec, current: str, target: str) -> bool:
    if current not in spec.states or target not in spec.states:
        return False
    return target in spec.transitions.get(current, ())


def _limit_int(spec: SearchProfilePolicySpec, name: str, default: int) -> int:
    value = spec.limits.get(name)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def _optional_number(value: object) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return float(value)


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None
