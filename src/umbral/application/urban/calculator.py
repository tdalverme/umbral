"""Pure deterministic execution of the urban contract.

Given precomputed primitives per listing (counts and nearest distances), this
module computes raw signal values (0-1) following the two-level declarative
contract: base signals combine primitives, composite signals combine base
signals. The calculator performs no I/O and is fully testable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from umbral.application.urban.confidence import input_coverage_confidence
from umbral.application.urban.contract import (
    CompositeSignalSpec,
    SignalSpec,
    SignalTerm,
    UrbanContract,
)


@dataclass(frozen=True, slots=True)
class SignalValue:
    value: float
    confidence: float
    missing: bool
    inputs_present: int
    inputs_total: int
    contributors: tuple[Mapping[str, object], ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class UrbanSignalResult:
    signals: Mapping[str, SignalValue]
    contract_version: str

    def for_signal(self, name: str) -> SignalValue | None:
        return self.signals.get(name)


class UrbanSignalCalculator:
    """Execute the urban contract over primitives for one listing."""

    def __init__(self, contract: UrbanContract) -> None:
        self.contract = contract

    def calculate(
        self,
        *,
        poi_distances: Mapping[str, Mapping[str, list[float]]] | None = None,
        linear_distances: Mapping[str, Mapping[str, list[float]]] | None = None,
    ) -> UrbanSignalResult:
        """Compute base and composite signals from precomputed distance buckets.

        Metrics live under the primitive metric names (count_300m, count_600m,
        nearest_m).
        """
        poi = dict(poi_distances or {})
        linear = dict(linear_distances or {})
        buckets: Mapping[str, Mapping[str, list[float]]] = {**poi, **linear}

        base_values: dict[str, SignalValue] = {}
        for signal in self.contract.signals:
            base_values[signal.name] = self._compute_base(signal, buckets)

        composite_values: dict[str, SignalValue] = {}
        for composite in self.contract.composite_signals:
            composite_values[composite.name] = self._compute_composite(
                composite, base_values
            )

        return UrbanSignalResult(
            signals={**base_values, **composite_values},
            contract_version=self.contract.contract_version,
        )

    def _compute_base(
        self,
        signal: SignalSpec,
        buckets: Mapping[str, Mapping[str, list[float]]],
    ) -> SignalValue:
        inputs_present = 0
        inputs_total = len(signal.formula)
        total = 0.0
        contributors: list[Mapping[str, object]] = []
        for term in signal.formula:
            present = self._term_present(term, buckets)
            if not present:
                continue
            inputs_present += 1
            score = self._score_term(term, buckets)
            total += term.weight * score
            contributors.append(
                {
                    "term": _term_label(term),
                    "score": round(score, 6),
                }
            )
        missing = inputs_present == 0
        value = round(max(0.0, min(1.0, total)), 4)
        confidence = input_coverage_confidence(
            present=inputs_present,
            total=inputs_total,
            spec=self.contract.confidence,
        )
        return SignalValue(
            value=value,
            confidence=confidence,
            missing=missing,
            inputs_present=inputs_present,
            inputs_total=inputs_total,
            contributors=tuple(contributors),
        )

    def _compute_composite(
        self,
        composite: CompositeSignalSpec,
        base_values: Mapping[str, SignalValue],
    ) -> SignalValue:
        inputs_present = 0
        inputs_total = len(composite.formula)
        total = 0.0
        contributors: list[Mapping[str, object]] = []
        for term in composite.formula:
            ref = term.signal_ref
            if ref is None:
                continue
            base = base_values.get(ref)
            if base is None or base.missing:
                continue
            inputs_present += 1
            score = (1.0 - base.value) if term.invert else base.value
            total += term.weight * score
            contributors.append(
                {
                    "term": ref,
                    "score": round(score, 6),
                    "confidence": base.confidence,
                }
            )
        missing = inputs_present == 0
        value = round(max(0.0, min(1.0, total)), 4)
        confidence = input_coverage_confidence(
            present=inputs_present,
            total=inputs_total,
            spec=self.contract.confidence,
        )
        return SignalValue(
            value=value,
            confidence=confidence,
            missing=missing,
            inputs_present=inputs_present,
            inputs_total=inputs_total,
            contributors=tuple(contributors),
        )

    def _term_present(
        self,
        term: SignalTerm,
        buckets: Mapping[str, Mapping[str, list[float]]],
    ) -> bool:
        if term.primitive_ref is None:
            return False
        category, metric = _split_ref(term.primitive_ref)
        return bool(buckets.get(category, {}).get(metric))

    def _score_term(
        self,
        term: SignalTerm,
        buckets: Mapping[str, Mapping[str, list[float]]],
    ) -> float:
        if term.primitive_ref is None:
            return 0.0
        category, metric = _split_ref(term.primitive_ref)
        distances = buckets.get(category, {}).get(metric) or []
        if not distances:
            return 0.0
        if term.op == "count":
            radius = _radius_for_metric(metric)
            target = term.target or 1
            count = sum(1 for distance in distances if distance <= radius)
            return _clamp01(count / max(1, target))
        best = min(distances)
        near = term.near if term.near is not None else 0.0
        far = term.far if term.far is not None else 1.0
        if best <= near:
            return 1.0
        if best >= far:
            return 0.0
        return _clamp01(1 - ((best - near) / (far - near)))

def _term_label(term: SignalTerm) -> str:
    return term.primitive_ref or term.signal_ref or ""


def _split_ref(ref: str) -> tuple[str, str]:
    category, _, metric = ref.partition(".")
    return category, metric


def _radius_for_metric(metric: str) -> float:
    if metric.startswith("count_"):
        for suffix in ("m",):
            candidate = metric.removeprefix("count_").removesuffix(suffix)
            try:
                return float(candidate)
            except ValueError:
                continue
    return 300.0


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))
