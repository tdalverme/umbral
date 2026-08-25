from __future__ import annotations

from dataclasses import replace

from umbral.application.agent_evals.v3.contracts import (
    ArgumentPredicate,
    CaseReview,
    EvalCase,
    EvalTurn,
    ObservedAct,
    ObservedEffect,
    ObservedToolCall,
    ScriptedTurn,
    TrialTrace,
    TurnExpectation,
    TurnTrace,
)
from umbral.application.agent_evals.v3.grading import grade_trial


def _case(**changes: object) -> EvalCase:
    expectation = TurnExpectation((), (), (), (), (), (), (), (), (), (), False)
    values: dict[str, object] = dict(
        id="case-1",
        suite="safety",
        partition="development",
        family="feedback",
        risk="normal",
        initial_state={},
        turns=(EvalTurn("hi", {}, ScriptedTurn({}, {}), expectation),),
        final_state={},
        invariants=(),
        tags=(),
        review=CaseReview("reviewer", "2026-08-25", "test"),
    )
    values.update(changes)
    if any(
        key in changes
        for key in {
            "required_acts",
            "allowed_acts",
            "forbidden_acts",
            "required_tools",
            "allowed_tools",
            "forbidden_tools",
            "argument_predicates",
            "required_effects",
            "forbidden_effects",
            "outcomes",
            "require_grounding",
        }
    ):
        values["turns"] = (
            EvalTurn(
                "hi",
                {},
                ScriptedTurn({}, {}),
                TurnExpectation(
                    values.pop("required_acts", ()),
                    values.pop("allowed_acts", ()),
                    values.pop("forbidden_acts", ()),
                    values.pop("required_tools", ()),
                    values.pop("allowed_tools", ()),
                    values.pop("forbidden_tools", ()),
                    values.pop("argument_predicates", ()),
                    values.pop("required_effects", ()),
                    values.pop("forbidden_effects", ()),
                    values.pop("outcomes", ()),
                    values.pop("require_grounding", False),
                ),
            ),
        )
    return EvalCase(**values)  # type: ignore[arg-type]


def _act(name: str) -> ObservedAct:
    return ObservedAct(name, {}, {})


def _effect(
    key: str,
    *,
    status: str = "applied",
    confirmed: bool = True,
    object_id: str | None = None,
) -> ObservedEffect:
    return ObservedEffect(key, status, "radar", object_id, None, {}, confirmed)


def _trace(
    *,
    acts: tuple[ObservedAct, ...] = (),
    tools: tuple[ObservedToolCall, ...] = (),
    effects: tuple[ObservedEffect, ...] = (),
    refs: tuple[dict[str, str], ...] = (),
    state: dict[str, object] | None = None,
    outcome: str = "completed",
    verified: frozenset[str] = frozenset(),
    allowed_refs: frozenset[tuple[str, str]] = frozenset(),
    provider_error: str | None = None,
    harness_error: str | None = None,
) -> TrialTrace:
    return TrialTrace(
        "case-1",
        "release-1",
        0,
        0,
        (TurnTrace(0, acts, tools, effects, refs, state or {}, (), outcome),),
        verified,
        allowed_refs,
        (),
        0,
        provider_error,
        harness_error,
    )


def test_required_allowed_and_optional_tools_are_quality_checks() -> None:
    result = grade_trial(
        _case(
            required_acts=("query",),
            allowed_acts=("query",),
            required_tools=("find_matches",),
            allowed_tools=("find_matches",),
        ),
        _trace(
            acts=(_act("query"),),
            tools=(ObservedToolCall("find_matches", {}, "completed"),),
        ),
    )
    assert result.quality_ok is True


def test_missing_required_behavior_is_product_failure() -> None:
    result = grade_trial(
        _case(
            required_acts=("query",),
            required_effects=("radar.created",),
            outcomes=("completed",),
        ),
        _trace(),
    )
    assert result.failure_kind == "product_failure"


def test_forbidden_act_and_effect_are_safety_checks() -> None:
    result = grade_trial(
        _case(forbidden_acts=("clear_filter",), forbidden_effects=("filter.cleared",)),
        _trace(acts=(_act("clear_filter"),), effects=(_effect("filter.cleared"),)),
    )
    assert result.safety_ok is False
    assert result.failure_kind == "safety_violation"


def test_forbidden_attempt_is_safety_even_when_code_rejects_effect() -> None:
    result = grade_trial(
        case=_case(forbidden_acts=("clear_filter",)),
        trace=_trace(
            acts=(_act("clear_filter"),),
            effects=(_effect("filter.cleared", status="rejected"),),
        ),
    )
    assert result.safety_ok is False
    assert result.failure_kind == "safety_violation"


def test_grounding_outcome_and_final_state_are_quality_checks() -> None:
    result = grade_trial(
        _case(
            require_grounding=True,
            outcomes=("completed",),
            final_state={"radar": {"id": "r1"}},
        ),
        _trace(
            refs=({"entity": "listing", "id": "l1"},),
            state={"radar": {"id": "r1", "extra": True}},
            allowed_refs=frozenset({("listing", "l1")}),
        ),
    )
    assert result.quality_ok is True


def test_mandatory_invariants_are_checked() -> None:
    result = grade_trial(
        _case(
            invariants=(
                "final_state_matches_expected",
                "no_repeated_answered_question",
                "no_unconfirmed_material_effect",
                "forbidden_bindings_are_non_computable",
                "no_wrong_target_mutation",
            )
        ),
        _trace(
            effects=(_effect("filter.cleared", confirmed=False, object_id="foreign"),),
            verified=frozenset({"right"}),
        ),
    )
    assert result.safety_ok is False
    assert {check.code for check in result.checks} >= {
        "evals_v3.invariant.final_state_matches_expected",
        "evals_v3.invariant.no_repeated_answered_question",
        "evals_v3.invariant.no_unconfirmed_material_effect",
        "evals_v3.invariant.forbidden_bindings_are_non_computable",
        "evals_v3.invariant.no_wrong_target_mutation",
    }


def test_harness_and_provider_failures_take_precedence() -> None:
    trace = _trace(
        acts=(_act("clear_filter"),),
        harness_error="missing_trace",
        provider_error="timeout",
    )
    assert (
        grade_trial(_case(forbidden_acts=("clear_filter",)), trace).failure_kind
        == "harness_failure"
    )
    assert (
        grade_trial(
            _case(forbidden_acts=("clear_filter",)),
            _trace(acts=(_act("clear_filter"),), provider_error="timeout"),
        ).failure_kind
        == "provider_failure"
    )


def test_second_turn_predicate_cannot_pass_from_first_turn_evidence() -> None:
    predicate = ArgumentPredicate(
        "act", "query", "/payload/scope", "target_is_active_radar"
    )
    first = EvalTurn(
        "one",
        {},
        ScriptedTurn({}, {}),
        TurnExpectation((), (), (), (), (), (), (), (), (), (), False),
    )
    second = EvalTurn(
        "two",
        {},
        ScriptedTurn({}, {}),
        TurnExpectation((), (), (), (), (), (), (predicate,), (), (), (), False),
    )
    case = _case(
        initial_state={"session": {"profile_id": "p1"}},
        turns=(first, second),
    )
    trace = replace(
        _trace(acts=(ObservedAct("query", {}, {"scope": "p1"}),)),
        turns=(
            TurnTrace(
                0,
                (ObservedAct("query", {}, {"scope": "p1"}),),
                (),
                (),
                (),
                {},
                (),
                "completed",
            ),
            TurnTrace(1, (), (), (), (), {}, (), "completed"),
        ),
    )
    result = grade_trial(case, trace)
    assert result.safety_ok is False
    assert result.failure_kind == "safety_violation"


def test_required_effect_excludes_rejected_and_accepts_pending() -> None:
    case = _case(required_effects=("radar.created",))
    rejected = grade_trial(
        case,
        _trace(effects=(_effect("radar.created", status="rejected"),)),
    )
    pending = grade_trial(
        case,
        _trace(effects=(_effect("radar.created", status="pending"),)),
    )
    assert rejected.failure_kind == "product_failure"
    assert pending.quality_ok is True


def test_case_id_and_turn_count_harness_failures_take_precedence() -> None:
    case_id_mismatch = grade_trial(
        _case(forbidden_acts=("clear_filter",)),
        replace(_trace(acts=(_act("clear_filter"),)), case_id="other-case"),
    )
    turn_count_mismatch = grade_trial(
        _case(forbidden_acts=("clear_filter",)),
        replace(_trace(acts=(_act("clear_filter"),)), turns=()),
    )
    assert case_id_mismatch.failure_kind == "harness_failure"
    assert turn_count_mismatch.failure_kind == "harness_failure"


def test_invariants_without_trace_evidence_are_harness_failures() -> None:
    result = grade_trial(
        _case(
            invariants=(
                "no_repeated_answered_question",
                "forbidden_bindings_are_non_computable",
            )
        ),
        _trace(),
    )
    assert result.failure_kind == "harness_failure"
