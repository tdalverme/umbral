"""Pure runner that evaluates the golden dataset under one release (R-03).

The runner is transport-agnostic: it consumes a ``CaseExecutor`` port that
drives the real graph stack per case (implemented in infrastructure) and
derives the per-case metrics through :mod:`metrics`. The strict regression
gate lives in :mod:`regression`.
"""

from __future__ import annotations

from typing import Protocol

from umbral.application.agent_evals.contracts import (
    CaseEvalResult,
    CaseTrace,
    GatewayFidelity,
    GoldenConversationCase,
    GoldenDataset,
    GraphRelease,
    PriceTable,
)
from umbral.application.agent_evals.metrics import evaluate_case


class CaseExecutor(Protocol):
    """Drives one golden case through the real graph stack and records a trace."""

    def execute(
        self, *, case: GoldenConversationCase, release: GraphRelease
    ) -> CaseTrace: ...


def run_suite(
    *,
    executor: CaseExecutor,
    dataset: GoldenDataset,
    release: GraphRelease,
    price_table: PriceTable,
    gateway_fidelity: GatewayFidelity = "simulated",
) -> tuple[CaseEvalResult, ...]:
    """Evaluate every golden case under a release and return per-case results."""
    results: list[CaseEvalResult] = []
    for case in dataset.cases:
        trace = executor.execute(case=case, release=release)
        results.append(evaluate_case(case=case, trace=trace, price_table=price_table))
    return tuple(results)
