"""Unit tests of the pure budget policy evaluation (T032)."""

from __future__ import annotations

from umbral.application.agent.budgets import (
    BudgetConsumption,
    BudgetPolicy,
    evaluate_budget,
)

_POLICY = BudgetPolicy()


def test_ok_below_warning_ratio() -> None:
    verdict = evaluate_budget(
        policy=_POLICY,
        consumption=BudgetConsumption(session_tokens=1000, user_tokens=2000),
    )
    assert verdict.level == "ok"


def test_warning_when_ratio_crosses_threshold() -> None:
    verdict = evaluate_budget(
        policy=_POLICY,
        consumption=BudgetConsumption(
            session_tokens=int(_POLICY.session_token_cap * 0.9)
        ),
    )
    assert verdict.level == "warning"


def test_exhausted_when_session_token_cap_reached() -> None:
    verdict = evaluate_budget(
        policy=_POLICY,
        consumption=BudgetConsumption(
            session_tokens=_POLICY.session_token_cap, user_tokens=_POLICY.user_token_cap
        ),
    )
    assert verdict.level == "exhausted"
    assert verdict.kind == "session_tokens"


def test_exhausted_when_concurrency_cap_reached() -> None:
    verdict = evaluate_budget(
        policy=_POLICY,
        consumption=BudgetConsumption(active_user_runs=_POLICY.user_concurrency_cap),
    )
    assert verdict.level == "exhausted"
    assert verdict.kind == "concurrency"


def test_exhausted_when_cost_cap_reached() -> None:
    verdict = evaluate_budget(
        policy=_POLICY,
        consumption=BudgetConsumption(user_cost_usd=_POLICY.user_cost_cap_usd),
    )
    assert verdict.level == "exhausted"
    assert verdict.kind == "user_cost"


def test_exhausted_when_tool_call_cap_reached() -> None:
    verdict = evaluate_budget(
        policy=_POLICY,
        consumption=BudgetConsumption(
            session_tool_calls=_POLICY.session_tool_call_cap
        ),
    )
    assert verdict.level == "exhausted"
    assert verdict.kind == "session_tool_calls"


def test_custom_policy_defaults_are_safe() -> None:
    assert _POLICY.window_hours == 24
    assert _POLICY.warning_ratio == 0.8
