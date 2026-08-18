"""US2 T023: percentile normalization semantics (scope, sample, fallback)."""

from __future__ import annotations

import pytest

from umbral.application.urban.contract import NormalizationSpec
from umbral.application.urban.normalization import (
    apply_confidence_penalty,
    compute_barrio_stats,
    normalize,
    percentile_of,
)
from umbral.infrastructure.urban.contract_loader import load_urban_contract_published

_SPEC = NormalizationSpec(
    method="percentile",
    min_sample_per_barrio=10,
    fallback_scope="caba",
    confidence_penalty=0.3,
)


def test_scope_decision_uses_min_sample() -> None:
    low = compute_barrio_stats(
        barrio="Caballito",
        signal="cafe_lifestyle",
        values=[0.1] * 5,
        spec=_SPEC,
    )
    assert low.normalization_scope == "caba"
    enough = compute_barrio_stats(
        barrio="Caballito",
        signal="cafe_lifestyle",
        values=[float(i) / 10 for i in range(10)],
        spec=_SPEC,
    )
    assert enough.normalization_scope == "barrio"


def test_tiny_sample_uses_flat_distribution() -> None:
    stat = compute_barrio_stats(
        barrio="Palermo",
        signal="cafe_lifestyle",
        values=[0.5, 0.5],
        spec=_SPEC,
    )
    assert stat.sample_size == 2
    assert stat.p50 == 0.5
    assert stat.p75 == 0.5
    assert stat.p90 == 0.5


def test_percentile_of_rank() -> None:
    assert percentile_of(0.5, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]) == pytest.approx(0.6667)
    assert percentile_of(1.0, [0.1, 0.2, 0.3]) == 1.0
    assert percentile_of(0.0, []) == 0.5


def test_normalize_uses_scope_and_clamps() -> None:
    result = normalize(
        raw_value=0.8, signal_values=[0.1, 0.2, 0.3, 0.4], scope="barrio"
    )
    assert result.normalization_scope == "barrio"
    assert result.normalized_value == pytest.approx(1.0)
    assert 0.0 <= result.value <= 1.0


def test_confidence_penalty_reduces_confidence() -> None:
    assert apply_confidence_penalty(1.0, 0.3) == pytest.approx(0.7)
    assert apply_confidence_penalty(0.5, 0.0) == pytest.approx(0.5)


def test_contract_normalization_flags_match() -> None:
    contract = load_urban_contract_published()
    assert contract.normalization.method == "percentile"
    assert contract.normalization.fallback_scope == "caba"
    assert contract.normalization.min_sample_per_barrio == 10
