"""Pure concept registry rules loaded from the criteria contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from umbral.application.criteria.contracts import MatcherType

_SUPPORTED_MATCHER_TYPES: tuple[MatcherType, ...] = (
    "numeric_range",
    "categorical",
    "geo_proximity",
    "semantic_feature",
)


class ConceptLike(Protocol):
    """Minimal concept surface consumed by the registry and the compiler."""

    @property
    def key(self) -> str: ...

    @property
    def aliases(self) -> tuple[str, ...]: ...

    @property
    def matcher_type(self) -> str: ...

    @property
    def params_schema(self) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class ConceptSeed:
    """One curated concept as published by the seed contract."""

    key: str
    name: str
    aliases: tuple[str, ...]
    matcher_type: MatcherType
    params_schema: Mapping[str, object]
    source: str
    defaults: Mapping[str, object]
    compute_policy: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class MatcherTypeSpec:
    """Declared parameter surface of one matcher type."""

    name: MatcherType
    allowed_params: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatcherTypesSpec:
    contract_version: str
    registry_version: str
    matcher_types: Mapping[MatcherType, MatcherTypeSpec]


@dataclass(frozen=True, slots=True)
class ConceptsSeedSpec:
    contract_version: str
    seed_version: str
    concepts: tuple[ConceptSeed, ...]


def parse_matcher_types(data: Mapping[str, object]) -> MatcherTypesSpec:
    if data.get("contract_version") != "1":
        raise ValueError("unsupported matcher types document version")
    registry_version = data.get("registry_version")
    if not isinstance(registry_version, str) or not registry_version:
        raise ValueError("registry_version is required")
    raw_types = data.get("matcher_types")
    if not isinstance(raw_types, Mapping):
        raise ValueError("matcher_types are required")
    parsed: dict[MatcherType, MatcherTypeSpec] = {}
    for name, raw in raw_types.items():
        if name not in _SUPPORTED_MATCHER_TYPES:
            raise ValueError(f"unsupported matcher type: {name}")
        if not isinstance(raw, Mapping):
            raise ValueError(f"matcher type {name} must be an object")
        allowed = raw.get("allowed_params")
        if not isinstance(allowed, list) or not all(
            isinstance(item, str) for item in allowed
        ):
            raise ValueError(f"matcher type {name} must declare allowed_params")
        parsed[cast(MatcherType, name)] = MatcherTypeSpec(
            name=cast(MatcherType, name),
            allowed_params=tuple(str(item) for item in allowed),
        )
    return MatcherTypesSpec(
        contract_version=str(data["contract_version"]),
        registry_version=registry_version,
        matcher_types=parsed,
    )


def parse_concepts_seed(data: Mapping[str, object]) -> ConceptsSeedSpec:
    if data.get("contract_version") != "1":
        raise ValueError("unsupported concepts seed document version")
    seed_version = data.get("seed_version")
    if not isinstance(seed_version, str) or not seed_version:
        raise ValueError("seed_version is required")
    raw_concepts = data.get("concepts")
    if not isinstance(raw_concepts, list):
        raise ValueError("concepts are required")
    concepts: list[ConceptSeed] = []
    for raw in raw_concepts:
        if not isinstance(raw, Mapping):
            raise ValueError("each concept must be an object")
        concepts.append(
            ConceptSeed(
                key=str(raw["key"]),
                name=str(raw["name"]),
                aliases=tuple(str(item) for item in raw.get("aliases", [])),
                matcher_type=str(raw["matcher_type"]),  # type: ignore[arg-type]
                params_schema=_as_mapping(raw.get("params_schema", {})),
                source=str(raw.get("source", "seed")),
                defaults=_as_mapping(raw.get("defaults", {})),
                compute_policy=_as_mapping(raw.get("compute_policy", {})),
            )
        )
    return ConceptsSeedSpec(
        contract_version=str(data["contract_version"]),
        seed_version=seed_version,
        concepts=tuple(concepts),
    )


def validate_concept_seed(
    seed: ConceptSeed, matcher_types: MatcherTypesSpec
) -> tuple[str, ...]:
    """Return the validation error codes of a concept seed, empty when valid."""

    errors: list[str] = []
    if not seed.key or len(seed.key) > 100:
        errors.append("criteria.concept_key_invalid")
    if len(seed.name) > 200:
        errors.append("criteria.concept_name_too_long")
    if len(seed.aliases) > 20:
        errors.append("criteria.concept_aliases_too_many")
    spec = matcher_types.matcher_types.get(seed.matcher_type)
    if spec is None:
        errors.append(f"criteria.unsupported_matcher_type:{seed.matcher_type}")
    else:
        for param in seed.params_schema:
            if param not in spec.allowed_params:
                errors.append(f"criteria.invalid_param:{seed.matcher_type}:{param}")
    return tuple(errors)


def resolve_alias(concepts: Mapping[str, ConceptLike], alias: str) -> str | None:
    """Resolve an alias (or canonical key) to one canonical concept key."""

    lowered = alias.strip().lower()
    if lowered in concepts:
        return lowered
    for concept in concepts.values():
        if lowered in {item.lower() for item in concept.aliases}:
            return concept.key
    return None


def detect_alias_collisions(
    concepts: Mapping[str, ConceptSeed],
) -> tuple[str, ...]:
    """Return explicit warnings for aliases shared by more than one concept."""

    owners: dict[str, list[str]] = {}
    for concept in concepts.values():
        for alias in concept.aliases:
            owners.setdefault(alias.lower(), []).append(concept.key)
    return tuple(
        f"alias_collision:{alias}:{','.join(sorted(keys))}"
        for alias, keys in owners.items()
        if len(keys) > 1
    )


def _as_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("expected an object mapping")
    return {str(key): item for key, item in value.items()}
