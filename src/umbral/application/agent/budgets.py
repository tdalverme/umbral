"""Pure budget policy evaluation for the conversational agent (research R-09).

Budget consumption is computed from already-persisted run records (tokens,
tool calls, cost via the price table, active runs for concurrency); this
module only evaluates a policy against a consumption snapshot, keeping the
enforcement deterministic and auditable (FR-012..FR-016).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from umbral.application.agent.contracts import BudgetVerdict


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    """Versioned per-user/per-session budget limits (plan values, Q3)."""

    window_hours: int = 24
    session_token_cap: int = 150000
    user_token_cap: int = 500000
    session_tool_call_cap: int = 40
    user_cost_cap_usd: float = 5.0
    user_concurrency_cap: int = 2
    warning_ratio: float = 0.8


@dataclass(frozen=True, slots=True)
class BudgetConsumption:
    """Snapshot of consumption for one user/session inside the window."""

    session_tokens: int = 0
    user_tokens: int = 0
    session_tool_calls: int = 0
    user_cost_usd: float = 0.0
    active_user_runs: int = 0


class BudgetConsumptionSource(Protocol):
    """Reads consumption from persisted runs for a user/session."""

    def consumption(
        self, *, user_id: UUID, session_id: UUID, since: object
    ) -> BudgetConsumption: ...


class BudgetGate(Protocol):
    """Evaluates the budget before a run; raises typed errors on exhaustion."""

    def check(self, *, user_id: UUID, session_id: UUID) -> BudgetVerdict: ...


def evaluate_budget(
    *, policy: BudgetPolicy, consumption: BudgetConsumption
) -> BudgetVerdict:
    """Evaluate a consumption snapshot against a policy.

    Returns ``exhausted`` with the limiting kind when any cap is reached, and
    ``warning`` when the highest ratio crosses the warning threshold (FR-013/
    FR-014).
    """
    ratios: list[tuple[str, float]] = []
    if policy.session_token_cap > 0:
        ratios.append(
            ("session_tokens", consumption.session_tokens / policy.session_token_cap)
        )
    if policy.user_token_cap > 0:
        ratios.append(("user_tokens", consumption.user_tokens / policy.user_token_cap))
    if policy.session_tool_call_cap > 0:
        ratios.append(
            (
                "session_tool_calls",
                consumption.session_tool_calls / policy.session_tool_call_cap,
            )
        )
    if policy.user_cost_cap_usd > 0:
        ratios.append(
            (
                "user_cost",
                consumption.user_cost_usd / policy.user_cost_cap_usd,
            )
        )
    if policy.user_concurrency_cap > 0:
        ratios.append(
            (
                "concurrency",
                consumption.active_user_runs / policy.user_concurrency_cap,
            )
        )
    if not ratios:
        return BudgetVerdict(level="ok")
    worst_kind, worst_ratio = max(ratios, key=lambda item: item[1])
    if worst_ratio >= 1.0:
        return BudgetVerdict(level="exhausted", kind=worst_kind, ratio=worst_ratio)
    if worst_ratio >= policy.warning_ratio:
        return BudgetVerdict(level="warning", kind=worst_kind, ratio=worst_ratio)
    return BudgetVerdict(level="ok", ratio=worst_ratio)
