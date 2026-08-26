from __future__ import annotations

import pytest

from umbral.application.agent_evals.v3.contracts import EvalV3ValidationError
from umbral.application.agent_evals.v3.statistics import wilson_interval


@pytest.mark.parametrize(
    ("successes", "trials", "expected_lower", "expected_upper"),
    [
        (0, 10, 0.0, 0.2775),
        (5, 10, 0.2366, 0.7634),
        (10, 10, 0.7225, 1.0),
    ],
)
def test_wilson_interval_matches_reference_values(
    successes: int, trials: int, expected_lower: float, expected_upper: float
) -> None:
    interval = wilson_interval(successes, trials, 0.95)

    assert interval.lower == pytest.approx(expected_lower, abs=1e-4)
    assert interval.upper == pytest.approx(expected_upper, abs=1e-4)


def test_wilson_interval_rejects_empty_trials() -> None:
    with pytest.raises(EvalV3ValidationError) as raised:
        wilson_interval(0, 0, 0.95)

    assert raised.value.error_codes == ("agent_evals_v3.empty_trials",)