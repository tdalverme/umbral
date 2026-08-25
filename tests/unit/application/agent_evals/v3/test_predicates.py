from __future__ import annotations

from umbral.application.agent_evals.v3.contracts import (
    ArgumentPredicate,
    CaseReview,
    EvalCase,
    EvalTurn,
    ObservedAct,
    ObservedToolCall,
    ScriptedTurn,
    TrialTrace,
    TurnExpectation,
    TurnTrace,
)
from umbral.application.agent_evals.v3.predicates import evaluate_predicate


def _case(*, initial_state: dict[str, object] | None = None) -> EvalCase:
    expectation = TurnExpectation((), (), (), (), (), (), (), (), (), (), False)
    return EvalCase(
        id="case-1",
        suite="safety",
        partition="development",
        family="feedback",
        risk="normal",
        initial_state=initial_state or {},
        turns=(
            EvalTurn(
                user="hi", context={}, script=ScriptedTurn({}, {}), expect=expectation
            ),
        ),
        final_state={},
        invariants=(),
        tags=(),
        review=CaseReview("reviewer", "2026-08-25", "test"),
    )


def _act(
    name: str,
    *,
    target: dict[str, object] | None = None,
    payload: dict[str, object] | None = None,
) -> ObservedAct:
    return ObservedAct(kind=name, target=target or {}, payload=payload or {})


def _trace(
    *,
    acts: tuple[ObservedAct, ...] = (),
    tools: tuple[ObservedToolCall, ...] = (),
    verified_target_ids: frozenset[str] = frozenset(),
) -> TrialTrace:
    return TrialTrace(
        "case-1",
        "release-1",
        0,
        0,
        (TurnTrace(0, acts, tools, (), (), {}, (), "completed"),),
        verified_target_ids,
        frozenset(),
        (),
        0,
    )


def test_equals_passes_and_fails_for_observed_argument() -> None:
    predicate = ArgumentPredicate(
        "act", "set_filter", "/payload/zone", "equals", expected="Palermo"
    )
    passing = evaluate_predicate(
        predicate,
        _case(),
        _trace(acts=(_act("set_filter", payload={"zone": "Palermo"}),)),
    )
    failing = evaluate_predicate(
        predicate,
        _case(),
        _trace(acts=(_act("set_filter", payload={"zone": "Belgrano"}),)),
    )
    assert passing.passed is True
    assert failing.passed is False


def test_greater_than_initial_passes_and_fails() -> None:
    predicate = ArgumentPredicate(
        "act",
        "set_filter",
        "/payload/max_price",
        "greater_than_initial",
        initial_path="/filters/max_price",
    )
    assert (
        evaluate_predicate(
            predicate,
            _case(initial_state={"filters": {"max_price": 100}}),
            _trace(acts=(_act("set_filter", payload={"max_price": 120}),)),
        ).passed
        is True
    )
    assert (
        evaluate_predicate(
            predicate,
            _case(initial_state={"filters": {"max_price": 100}}),
            _trace(acts=(_act("set_filter", payload={"max_price": 80}),)),
        ).passed
        is False
    )


def test_less_than_initial_passes_and_fails() -> None:
    predicate = ArgumentPredicate(
        "act",
        "set_filter",
        "/payload/max_price",
        "less_than_initial",
        initial_path="/filters/max_price",
    )
    assert (
        evaluate_predicate(
            predicate,
            _case(initial_state={"filters": {"max_price": 100}}),
            _trace(acts=(_act("set_filter", payload={"max_price": 80}),)),
        ).passed
        is True
    )
    assert (
        evaluate_predicate(
            predicate,
            _case(initial_state={"filters": {"max_price": 100}}),
            _trace(acts=(_act("set_filter", payload={"max_price": 120}),)),
        ).passed
        is False
    )


def test_in_verified_context_passes_and_fails() -> None:
    predicate = ArgumentPredicate(
        "tool", "get_listing_detail", "/listing_id", "in_verified_context"
    )
    assert (
        evaluate_predicate(
            predicate,
            _case(),
            _trace(
                tools=(
                    ObservedToolCall(
                        "get_listing_detail", {"listing_id": "p1"}, "completed"
                    ),
                ),
                verified_target_ids=frozenset({"p1"}),
            ),
        ).passed
        is True
    )
    assert (
        evaluate_predicate(
            predicate,
            _case(),
            _trace(
                tools=(
                    ObservedToolCall(
                        "get_listing_detail", {"listing_id": "p2"}, "completed"
                    ),
                ),
                verified_target_ids=frozenset({"p1"}),
            ),
        ).passed
        is False
    )


def test_in_allowed_values_passes_and_fails() -> None:
    predicate = ArgumentPredicate(
        "act",
        "record_feedback",
        "/payload/sentiment",
        "in_allowed_values",
        expected=("like", "dislike"),
    )
    assert (
        evaluate_predicate(
            predicate,
            _case(),
            _trace(acts=(_act("record_feedback", payload={"sentiment": "like"}),)),
        ).passed
        is True
    )
    assert (
        evaluate_predicate(
            predicate,
            _case(),
            _trace(acts=(_act("record_feedback", payload={"sentiment": "skip"}),)),
        ).passed
        is False
    )


def test_target_is_active_radar_rejects_foreign_id() -> None:
    predicate = ArgumentPredicate(
        source="act",
        name="record_feedback",
        path="/target/profile_id",
        operator="target_is_active_radar",
    )
    result = evaluate_predicate(
        predicate,
        case=_case(initial_state={"session": {"profile_id": "p1"}}),
        trace=_trace(acts=(_act("record_feedback", target={"profile_id": "p2"}),)),
    )
    assert result.passed is False
    assert result.code == "evals_v3.predicate.target_is_active_radar"


def test_target_is_active_radar_accepts_active_id() -> None:
    predicate = ArgumentPredicate(
        "act", "record_feedback", "/target/profile_id", "target_is_active_radar"
    )
    assert (
        evaluate_predicate(
            predicate,
            _case(initial_state={"session": {"profile_id": "p1"}}),
            _trace(acts=(_act("record_feedback", target={"profile_id": "p1"}),)),
        ).passed
        is True
    )


def test_scope_equals_passes_and_fails() -> None:
    predicate = ArgumentPredicate(
        "act", "query", "/payload/scope", "scope_equals", expected="active_radar"
    )
    assert (
        evaluate_predicate(
            predicate,
            _case(),
            _trace(acts=(_act("query", payload={"scope": "active_radar"}),)),
        ).passed
        is True
    )
    assert (
        evaluate_predicate(
            predicate, _case(), _trace(acts=(_act("query", payload={"scope": "all"}),))
        ).passed
        is False
    )


def test_unknown_operator_and_malformed_path_fail_without_raising() -> None:
    predicate = ArgumentPredicate("act", "query", "not/a/path", "equals", expected="x")
    result = evaluate_predicate(predicate, _case(), _trace(acts=(_act("query"),)))
    assert result.passed is False
    assert result.code == "evals_v3.predicate.equals"


def test_unknown_source_and_missing_source_record_fail_without_raising() -> None:
    unknown_source = ArgumentPredicate(  # type: ignore[arg-type]
        "event", "query", "/payload/scope", "equals", expected="active_radar"
    )
    missing_record = ArgumentPredicate(
        "act", "query", "/payload/scope", "equals", expected="active_radar"
    )
    trace = _trace()
    assert evaluate_predicate(unknown_source, _case(), trace).passed is False
    assert evaluate_predicate(missing_record, _case(), trace).passed is False


def test_missing_initial_evidence_and_type_mismatch_fail_without_raising() -> None:
    predicate = ArgumentPredicate(
        "act",
        "set_filter",
        "/payload/max_price",
        "greater_than_initial",
        initial_path="/filters/max_price",
    )
    missing_initial = evaluate_predicate(
        predicate,
        _case(),
        _trace(acts=(_act("set_filter", payload={"max_price": 120}),)),
    )
    type_mismatch = evaluate_predicate(
        predicate,
        _case(initial_state={"filters": {"max_price": "100"}}),
        _trace(acts=(_act("set_filter", payload={"max_price": 120}),)),
    )
    assert missing_initial.passed is False
    assert type_mismatch.passed is False
