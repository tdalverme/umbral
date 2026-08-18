"""Declarative per-barrio percentile normalization for urban signals."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import quantiles

from umbral.application.urban.contract import NormalizationSpec


@dataclass(frozen=True, slots=True)
class BarrioStat:
    """Precomputed percentile distribution for one barrio and signal."""

    barrio: str
    signal: str
    sample_size: int
    normalization_scope: str
    p50: float
    p75: float
    p90: float


@dataclass(frozen=True, slots=True)
class NormalizedSignal:
    """Raw signal normalized against its barrio (or fallback)."""

    value: float
    normalized_value: float
    normalization_scope: str
    percentile: float


def compute_barrio_stats(
    *,
    barrio: str,
    signal: str,
    values: Sequence[float],
    spec: NormalizationSpec,
) -> BarrioStat:
    """Precompute percentiles, deciding barrio vs fallback by sample size.

    The decision is stable for the whole job and stored per barrio+signal.
    """
    valid = [value for value in values if value is not None]
    scope = (
        "barrio"
        if len(valid) >= spec.min_sample_per_barrio
        else spec.fallback_scope
    )
    if len(valid) < 3:
        return BarrioStat(
            barrio=barrio,
            signal=signal,
            sample_size=len(valid),
            normalization_scope=scope,
            p50=0.5,
            p75=0.5,
            p90=0.5,
        )
    q = quantiles(sorted(valid), n=10)
    p50 = q[4]
    p75 = q[7]
    p90 = q[8]
    return BarrioStat(
        barrio=barrio,
        signal=signal,
        sample_size=len(valid),
        normalization_scope=scope,
        p50=p50,
        p75=p75,
        p90=p90,
    )


def percentile_of(raw: float, values: Sequence[float]) -> float:
    """Percentile (0-1) of a raw value within a reference distribution."""
    if not values:
        return 0.5
    below = sum(1 for value in values if value < raw)
    return _clamp01(below / len(values))


def normalize(
    *,
    raw_value: float,
    signal_values: Sequence[float],
    scope: str,
) -> NormalizedSignal:
    """Normalize a raw signal against its barrio or fallback distribution.

    For barrio scope the reference is the barrio distribution; for fallback
    scope it is the city-wide distribution provided in ``signal_values``.
    """
    percentile = percentile_of(raw_value, signal_values)
    return NormalizedSignal(
        value=_clamp01(raw_value),
        normalized_value=_clamp01(percentile),
        normalization_scope=scope,
        percentile=percentile,
    )


def apply_confidence_penalty(confidence: float, penalty: float) -> float:
    return _clamp01(confidence * (1 - penalty)) if penalty > 0 else _clamp01(confidence)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))
