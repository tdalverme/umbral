"""Clarification policy unit tests (UM-H4-018, T021)."""

from __future__ import annotations

from umbral.agent.intent.clarification import decide, render_question

_KEYS = ("budget", "zona", "hard_filters", "radio")
_MIN = 0.6
_MAX = 2


def test_low_confidence_high_impact_triggers_clarification() -> None:
    plan = decide(
        intent="refinamiento",
        parameters=[{"key": "budget", "value": "900", "confidence": 0.4}],
        high_impact_missing=[],
        contradictions=[],
        high_impact_keys=_KEYS,
        min_confidence=_MIN,
        rounds=0,
        max_rounds=_MAX,
    )
    assert plan is not None
    assert "budget" in plan.pending_params
    assert plan.exceeded() is False


def test_high_confidence_high_impact_does_not_trigger() -> None:
    plan = decide(
        intent="refinamiento",
        parameters=[{"key": "budget", "value": "900", "confidence": 0.9}],
        high_impact_missing=[],
        contradictions=[],
        high_impact_keys=_KEYS,
        min_confidence=_MIN,
        rounds=0,
        max_rounds=_MAX,
    )
    assert plan is None


def test_missing_high_impact_parameter_triggers() -> None:
    plan = decide(
        intent="refinamiento",
        parameters=[],
        high_impact_missing=["zona"],
        contradictions=[],
        high_impact_keys=_KEYS,
        min_confidence=_MIN,
        rounds=0,
        max_rounds=_MAX,
    )
    assert plan is not None
    assert "zona" in plan.pending_params


def test_contradiction_triggers_clarification() -> None:
    plan = decide(
        intent="refinamiento",
        parameters=[{"key": "budget", "value": "700", "confidence": 0.9}],
        high_impact_missing=[],
        contradictions=[{"key": "budget", "current_value": "900", "requested": "700"}],
        high_impact_keys=_KEYS,
        min_confidence=_MIN,
        rounds=0,
        max_rounds=_MAX,
    )
    assert plan is not None
    assert "contradiccion" in plan.pending_params


def test_out_of_scope_never_clarifies() -> None:
    plan = decide(
        intent="fuera_de_alcance",
        parameters=[],
        high_impact_missing=["budget"],
        contradictions=[],
        high_impact_keys=_KEYS,
        min_confidence=_MIN,
        rounds=0,
        max_rounds=_MAX,
    )
    assert plan is None


def test_rounds_exhausted_renders_refusal() -> None:
    plan = decide(
        intent="refinamiento",
        parameters=[{"key": "budget", "value": "x", "confidence": 0.3}],
        high_impact_missing=[],
        contradictions=[],
        high_impact_keys=_KEYS,
        min_confidence=_MIN,
        rounds=_MAX,
        max_rounds=_MAX,
    )
    assert plan is not None
    assert plan.exceeded() is True
    assert "no puedo aplicar" in render_question(plan).lower()
