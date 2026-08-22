"""Loader and validation of the declarative urban contract."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_NORMALIZATION_SCOPES = frozenset({"barrio", "absolute"})
_OPS = frozenset({"count", "distance"})
_KINDS = frozenset({"density", "distance"})


class UrbanContractInvalid(ValueError):
    """The urban contract document violates its declared shape."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"urban_contract_invalid: {reason}")


@dataclass(frozen=True, slots=True)
class UrbanSource:
    name: str
    url: str
    license: str
    attribution: str


@dataclass(frozen=True, slots=True)
class TagMapping:
    category: str
    osm_tags: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class PrimitiveSpec:
    name: str
    kind: str  # count | nearest
    radius_m: int | None = None


@dataclass(frozen=True, slots=True)
class SignalTerm:
    weight: float
    op: str
    target: int | None = None
    near: float | None = None
    far: float | None = None
    primitive_ref: str | None = None
    signal_ref: str | None = None
    invert: bool = False


@dataclass(frozen=True, slots=True)
class SignalSpec:
    name: str
    kind: str  # density | distance
    normalized_by: str  # barrio | absolute
    formula: tuple[SignalTerm, ...]
    primitive_refs: tuple[str, ...] = ()
    signal_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompositeSignalSpec:
    name: str
    normalized_by: str
    formula: tuple[SignalTerm, ...]
    signal_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NormalizationSpec:
    method: str
    min_sample_per_barrio: int
    fallback_scope: str
    confidence_penalty: float


@dataclass(frozen=True, slots=True)
class ConfidenceSpec:
    method: str
    missing_penalty: float


@dataclass(frozen=True, slots=True)
class MissingSpec:
    value: object
    confidence: float


@dataclass(frozen=True, slots=True)
class UrbanContract:
    """Validated, executable interpretation of the urban contract."""

    contract_version: str
    source: UrbanSource
    tags_mapping: tuple[TagMapping, ...]
    linear_tags_mapping: tuple[TagMapping, ...]
    primitives: Mapping[str, tuple[PrimitiveSpec, ...]]
    linear_primitives: Mapping[str, tuple[PrimitiveSpec, ...]]
    signals: tuple[SignalSpec, ...]
    composite_signals: tuple[CompositeSignalSpec, ...]
    normalization: NormalizationSpec
    confidence: ConfidenceSpec
    missing: MissingSpec
    distance_radius_m: int

    def base_signal_names(self) -> frozenset[str]:
        return frozenset(signal.name for signal in self.signals)

    def signal_by_name(self, name: str) -> SignalSpec | None:
        return next(
            (signal for signal in self.signals if signal.name == name), None
        )

    def composite_by_name(self, name: str) -> CompositeSignalSpec | None:
        return next(
            (signal for signal in self.composite_signals if signal.name == name), None
        )

    def primitive_names(self) -> frozenset[str]:
        return frozenset(self.primitives) | frozenset(self.linear_primitives)


def load_urban_contract(path: Path) -> UrbanContract:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise UrbanContractInvalid("document must be a JSON object")
    return parse_urban_contract(raw)


def parse_urban_contract(data: Mapping[str, object]) -> UrbanContract:
    contract_version = _required_str(data.get("contract_version"), "contract_version")
    raw_source = data.get("source")
    if not isinstance(raw_source, Mapping):
        raise UrbanContractInvalid("source required")
    source = UrbanSource(
        name=_required_str(raw_source.get("name"), "source.name"),
        url=_required_str(raw_source.get("url"), "source.url"),
        license=_required_str(raw_source.get("license"), "source.license"),
        attribution=_required_str(
            raw_source.get("attribution"), "source.attribution"
        ),
    )
    tags_mapping = tuple(
        _parse_tag_mapping(item) for item in _as_list(data, "tags_mapping")
    )
    linear_tags_mapping = tuple(
        _parse_tag_mapping(item) for item in _as_list(data, "linear_tags_mapping")
    )
    primitives = _parse_primitives(data.get("primitives"))
    linear_primitives = _parse_primitives(data.get("linear_primitives"))
    raw_signals = _as_list(data, "signals")
    signals = tuple(
        _parse_signal(item, {**primitives, **linear_primitives})
        for item in raw_signals
    )
    base_names = frozenset(signal.name for signal in signals)
    if len(base_names) != len(signals):
        raise UrbanContractInvalid("duplicate signal name")
    raw_composites = _as_list(data, "composite_signals")
    composites: list[CompositeSignalSpec] = []
    known = set(base_names)
    for item in raw_composites:
        composite = _parse_composite(item, frozenset(known))
        known.add(composite.name)
        composites.append(composite)
    composites_tuple = tuple(composites)
    composite_names = {signal.name for signal in composites_tuple}
    if len(composite_names) != len(composites_tuple):
        raise UrbanContractInvalid("duplicate composite signal name")
    _check_composite_acyclic(composites_tuple)
    normalization = _parse_normalization(data.get("normalization"))
    confidence = _parse_confidence(data.get("confidence"))
    raw_missing = data.get("missing")
    missing_raw = (
        raw_missing.get("default")
        if isinstance(raw_missing, Mapping)
        else None
    )
    if not isinstance(missing_raw, Mapping):
        raise UrbanContractInvalid("missing.default required")
    missing = MissingSpec(
        value=missing_raw.get("value"),
        confidence=_number(missing_raw.get("confidence"), "missing.confidence"),
    )
    radius = _number(data.get("distance_radius_m"), "distance_radius_m")
    return UrbanContract(
        contract_version=contract_version,
        source=source,
        tags_mapping=tags_mapping,
        linear_tags_mapping=linear_tags_mapping,
        primitives=primitives,
        linear_primitives=linear_primitives,
        signals=signals,
        composite_signals=composites_tuple,
        normalization=normalization,
        confidence=confidence,
        missing=missing,
        distance_radius_m=int(radius),
    )


def _parse_tag_mapping(raw: object) -> TagMapping:
    if not isinstance(raw, Mapping):
        raise UrbanContractInvalid("tag mapping must be an object")
    category = _required_str(raw.get("category"), "tags_mapping.category")
    raw_tags = raw.get("osm_tags")
    if not isinstance(raw_tags, list) or not raw_tags:
        raise UrbanContractInvalid(f"tags_mapping.{category}.osm_tags required")
    tags: list[tuple[str, str]] = []
    for item in raw_tags:
        if not isinstance(item, list) or len(item) != 2 or not all(
            isinstance(part, str) for part in item
        ):
            raise UrbanContractInvalid(f"tags_mapping.{category}.bad_tag")
        tags.append((item[0], item[1]))
    return TagMapping(category=category, osm_tags=tuple(tags))


def _parse_primitives(raw: object) -> Mapping[str, tuple[PrimitiveSpec, ...]]:
    if not isinstance(raw, Mapping):
        raise UrbanContractInvalid("primitives required")
    result: dict[str, tuple[PrimitiveSpec, ...]] = {}
    for category, raw_metrics in raw.items():
        if not isinstance(raw_metrics, list):
            raise UrbanContractInvalid(f"primitives.{category} must be a list")
        metrics = []
        for metric in raw_metrics:
            if not isinstance(metric, Mapping):
                raise UrbanContractInvalid(f"primitives.{category}.bad_metric")
            name = _required_str(metric.get("name"), "primitives.metric.name")
            kind = _required_str(metric.get("kind"), "primitives.metric.kind")
            if kind not in {"count", "nearest"}:
                raise UrbanContractInvalid(f"primitives.{category}.{name}.bad_kind")
            radius = _optional_number(metric.get("radius_m"))
            if kind == "count" and radius is None:
                raise UrbanContractInvalid(
                    f"primitives.{category}.{name}.radius_required"
                )
            metrics.append(PrimitiveSpec(name=name, kind=kind, radius_m=radius))
        if not metrics:
            raise UrbanContractInvalid(f"primitives.{category}.empty")
        result[str(category)] = tuple(metrics)
    return result


def _parse_signal(
    raw: object, primitives: Mapping[str, tuple[PrimitiveSpec, ...]]
) -> SignalSpec:
    if not isinstance(raw, Mapping):
        raise UrbanContractInvalid("signal must be an object")
    name = _required_str(raw.get("name"), "signal.name")
    kind = _required_str(raw.get("kind"), f"signal.{name}.kind")
    if kind not in _KINDS:
        raise UrbanContractInvalid(f"signal.{name}.bad_kind")
    normalized_by = _required_str(
        raw.get("normalized_by"), f"signal.{name}.normalized_by"
    )
    if normalized_by not in _NORMALIZATION_SCOPES:
        raise UrbanContractInvalid(f"signal.{name}.bad_normalized_by")
    raw_formula = raw.get("formula")
    if not isinstance(raw_formula, Mapping):
        raise UrbanContractInvalid(f"signal.{name}.formula required")
    raw_terms = raw_formula.get("terms")
    if not isinstance(raw_terms, list) or not raw_terms:
        raise UrbanContractInvalid(f"signal.{name}.formula.terms required")
    terms, primitive_refs = _parse_terms(
        name, raw_terms, primitives, allow_signal=False
    )
    return SignalSpec(
        name=name,
        kind=kind,
        normalized_by=normalized_by,
        formula=tuple(terms),
        primitive_refs=tuple(sorted(primitive_refs)),
    )


def _parse_composite(raw: object, base_names: frozenset[str]) -> CompositeSignalSpec:
    if not isinstance(raw, Mapping):
        raise UrbanContractInvalid("composite signal must be an object")
    name = _required_str(raw.get("name"), "composite.name")
    normalized_by = _required_str(
        raw.get("normalized_by"), f"composite.{name}.normalized_by"
    )
    if normalized_by not in _NORMALIZATION_SCOPES:
        raise UrbanContractInvalid(f"composite.{name}.bad_normalized_by")
    raw_formula = raw.get("formula")
    if not isinstance(raw_formula, Mapping):
        raise UrbanContractInvalid(f"composite.{name}.formula required")
    raw_terms = raw_formula.get("terms")
    if not isinstance(raw_terms, list) or not raw_terms:
        raise UrbanContractInvalid(f"composite.{name}.formula.terms required")
    refs: set[str] = set()
    terms: list[SignalTerm] = []
    for term in raw_terms:
        if not isinstance(term, Mapping):
            raise UrbanContractInvalid(f"composite.{name}.bad_term")
        signal_ref = _required_str(term.get("signal"), f"composite.{name}.signal")
        if signal_ref not in base_names:
            raise UrbanContractInvalid(
                f"composite.{name} -> unknown signal {signal_ref}"
            )
        if signal_ref == name:
            raise UrbanContractInvalid(f"composite.{name} self-reference")
        refs.add(signal_ref)
        weight = _weight(term.get("weight"), f"composite.{name}.{signal_ref}.weight")
        invert = (
            term.get("invert", False)
            if isinstance(term.get("invert", False), bool)
            else False
        )
        terms.append(
            SignalTerm(
                weight=weight,
                op="signal",
                signal_ref=signal_ref,
                invert=invert,
            )
        )
    if not _weights_normalize(terms):
        raise UrbanContractInvalid(f"composite.{name}.weights_not_normalizing")
    return CompositeSignalSpec(
        name=name,
        normalized_by=normalized_by,
        formula=tuple(terms),
        signal_refs=tuple(sorted(refs)),
    )


def _parse_terms(
    signal_name: str,
    raw_terms: list[object],
    primitives: Mapping[str, tuple[PrimitiveSpec, ...]],
    *,
    allow_signal: bool,
) -> tuple[list[SignalTerm], set[str]]:
    refs: set[str] = set()
    terms: list[SignalTerm] = []
    for term in raw_terms:
        if not isinstance(term, Mapping):
            raise UrbanContractInvalid(f"signal.{signal_name}.bad_term")
        primitive = _required_str(
            term.get("primitive"), f"signal.{signal_name}.primitive"
        )
        if "." not in primitive:
            raise UrbanContractInvalid(f"signal.{signal_name}.bad_primitive_ref")
        category, metric = primitive.split(".", 1)
        spec = primitives.get(category)
        if spec is None:
            raise UrbanContractInvalid(
                f"signal.{signal_name} -> unknown category {category}"
            )
        if not any(m.name == metric for m in spec):
            raise UrbanContractInvalid(
                f"signal.{signal_name} -> unknown metric {metric}"
            )
        refs.add(primitive)
        op = _required_str(
            term.get("op"), f"signal.{signal_name}.{primitive}.op"
        )
        if op not in _OPS:
            raise UrbanContractInvalid(f"signal.{signal_name}.{primitive}.bad_op")
        metric_spec = next(
            metric_spec for metric_spec in spec if metric_spec.name == metric
        )
        if (op == "count" and metric_spec.kind != "count") or (
            op == "distance" and metric_spec.kind != "nearest"
        ):
            raise UrbanContractInvalid(
                f"signal.{signal_name}.{primitive}.operator_metric_mismatch"
            )
        weight = _weight(
            term.get("weight"), f"signal.{signal_name}.{primitive}.weight"
        )
        if op == "count":
            target = _int(
                term.get("target"), f"signal.{signal_name}.{primitive}.target"
            )
            terms.append(
                SignalTerm(
                    weight=weight,
                    op="count",
                    target=target,
                    primitive_ref=primitive,
                )
            )
        else:
            near = _number(term.get("near"), f"signal.{signal_name}.{primitive}.near")
            far = _number(term.get("far"), f"signal.{signal_name}.{primitive}.far")
            terms.append(
                SignalTerm(
                    weight=weight,
                    op="distance",
                    near=near,
                    far=far,
                    primitive_ref=primitive,
                )
            )
    if not _weights_normalize(terms):
        raise UrbanContractInvalid(f"signal.{signal_name}.weights_not_normalizing")
    return terms, refs


def _parse_normalization(raw: object) -> NormalizationSpec:
    if not isinstance(raw, Mapping):
        raise UrbanContractInvalid("normalization required")
    method = _required_str(raw.get("method"), "normalization.method")
    if method != "percentile":
        raise UrbanContractInvalid("normalization.method must be percentile")
    min_sample = _int(raw.get("min_sample_per_barrio"), "normalization.min_sample")
    fallback = raw.get("fallback")
    if not isinstance(fallback, Mapping):
        raise UrbanContractInvalid("normalization.fallback required")
    scope = _required_str(fallback.get("scope"), "normalization.fallback.scope")
    penalty = _number(
        fallback.get("confidence_penalty"), "normalization.fallback.confidence_penalty"
    )
    return NormalizationSpec(
        method=method,
        min_sample_per_barrio=min_sample,
        fallback_scope=scope,
        confidence_penalty=penalty,
    )


def _parse_confidence(raw: object) -> ConfidenceSpec:
    if not isinstance(raw, Mapping):
        raise UrbanContractInvalid("confidence required")
    method = _required_str(raw.get("method"), "confidence.method")
    if method != "weighted_input_coverage":
        raise UrbanContractInvalid("confidence.method must be weighted_input_coverage")
    penalty = _number(raw.get("missing_penalty"), "confidence.missing_penalty")
    return ConfidenceSpec(method=method, missing_penalty=penalty)


def _check_composite_acyclic(composites: tuple[CompositeSignalSpec, ...]) -> None:
    deps: dict[str, set[str]] = {
        signal.name: set(signal.signal_refs) for signal in composites
    }
    visited: set[str] = set()
    stack: list[str] = []

    def visit(name: str) -> None:
        if name in stack:
            raise UrbanContractInvalid(
                f"composite cycle: {' -> '.join(stack + [name])}"
            )
        if name in visited:
            return
        stack.append(name)
        for dep in deps.get(name, ()):
            visit(dep)
        stack.pop()
        visited.add(name)

    for name in deps:
        visit(name)


def _weights_normalize(terms: list[SignalTerm]) -> bool:
    total = sum(term.weight for term in terms)
    return abs(total - 1.0) < 1e-6


def _as_list(data: Mapping[str, object], key: str) -> list[object]:
    value = data.get(key)
    if not isinstance(value, list):
        raise UrbanContractInvalid(f"{key} must be a list")
    return value


def _required_str(value: object, key: str) -> str:
    if not isinstance(value, str) or not value:
        raise UrbanContractInvalid(f"{key} required")
    return value


def _weight(value: object, key: str) -> float:
    if isinstance(value, bool):
        raise UrbanContractInvalid(f"{key} must be a number")
    if not isinstance(value, (int, float)):
        raise UrbanContractInvalid(f"{key} must be a number")
    return float(value)


def _number(value: object, key: str) -> float:
    if isinstance(value, bool):
        raise UrbanContractInvalid(f"{key} must be a number")
    if not isinstance(value, (int, float)):
        raise UrbanContractInvalid(f"{key} must be a number")
    return float(value)


def _optional_number(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UrbanContractInvalid("radius_m must be a number")
    return int(value)


def _int(value: object, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UrbanContractInvalid(f"{key} must be an integer")
    return value
