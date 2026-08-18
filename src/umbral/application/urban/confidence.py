"""Declarative confidence from input coverage (urban contract)."""

from __future__ import annotations

from umbral.application.urban.contract import ConfidenceSpec


def input_coverage_confidence(
    *,
    present: int,
    total: int,
    spec: ConfidenceSpec,
) -> float:
    """Confidence derived from the fraction of inputs with data.

    A signal with all inputs present scores full coverage; any missing input
    reduces coverage by the declared ``missing_penalty``. Returns a value in
    [0, 1].
    """
    if total <= 0:
        return 0.0
    coverage = present / total
    if coverage < 1.0:
        coverage *= 1 - spec.missing_penalty
    return max(0.0, min(1.0, round(coverage, 4)))
