"""Wilson score intervals for v3 case success rates.

Standard-library only: the required quantile comes from
``NormalDist().inv_cdf``. Rounding happens only at serialization time,
never inside the interval calculation.
"""

from __future__ import annotations

from statistics import NormalDist

from umbral.application.agent_evals.v3.contracts import (
    EvalV3ValidationError,
    Interval,
)


def wilson_interval(successes: int, trials: int, confidence_level: float) -> Interval:
    """Two-sided Wilson score interval for ``successes`` in ``trials``."""
    if trials <= 0:
        raise EvalV3ValidationError(("agent_evals_v3.empty_trials",))
    z = NormalDist().inv_cdf(0.5 + confidence_level / 2)
    ratio = z * z / trials
    center = (successes / trials + ratio / 2) / (1 + ratio)
    width = z * z / (4 * trials * trials)
    margin = (
        z
        / (1 + ratio)
        * (successes * (trials - successes) / trials**3 + width) ** 0.5
    )
    return Interval(
        lower=max(0.0, center - margin),
        upper=min(1.0, center + margin),
    )