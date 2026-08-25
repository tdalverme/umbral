"""Pure semantic checks for v3 structured trajectory evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Callable, TypeGuard

from umbral.application.agent_evals.v3.contracts import (
    ArgumentPredicate,
    CheckResult,
    EvalCase,
    TrialTrace,
)

_MISSING = object()


def evaluate_predicate(
    predicate: ArgumentPredicate, case: EvalCase, trace: TrialTrace
) -> CheckResult:
    """Evaluate one declared predicate without executing user-provided input."""
    code = f"evals_v3.predicate.{predicate.operator}"
    evaluator = _EVALUATORS.get(predicate.operator)
    if evaluator is None:
        return _failed(code, predicate.operator, "unknown_operator")
    records = _matching_records(predicate, trace)
    if not records:
        return _failed(code, predicate.operator, "missing_source_record")
    values = [_resolve_path(record, predicate.path) for record in records]
    if any(value is _MISSING for value in values):
        return _failed(code, predicate.operator, "missing_or_malformed_path")
    for value in values:
        passed, detail = evaluator(predicate, case, trace, value)
        if not passed:
            return CheckResult(
                code, False, predicate.operator == "target_is_active_radar", detail
            )
    return CheckResult(
        code,
        True,
        predicate.operator == "target_is_active_radar",
        "predicate_satisfied",
    )


def _matching_records(
    predicate: ArgumentPredicate, trace: TrialTrace
) -> tuple[Mapping[str, object], ...]:
    if predicate.source == "act":
        return tuple(
            {"kind": act.kind, "target": act.target, "payload": act.payload}
            for turn in trace.turns
            for act in turn.acts
            if act.kind == predicate.name
        )
    if predicate.source == "tool":
        return tuple(
            {"name": tool.name, **tool.args}
            for turn in trace.turns
            for tool in turn.tools
            if tool.name == predicate.name
        )
    return ()


def _resolve_path(source: object, path: str | None) -> object:
    if not isinstance(path, str) or not path.startswith("/"):
        return _MISSING
    current = source
    for part in path.split("/")[1:]:
        if not part or not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _equals(
    predicate: ArgumentPredicate, _: EvalCase, __: TrialTrace, value: object
) -> tuple[bool, str]:
    return value == predicate.expected, "value_does_not_equal_expected"


def _greater_than_initial(
    predicate: ArgumentPredicate, case: EvalCase, _: TrialTrace, value: object
) -> tuple[bool, str]:
    initial = _resolve_path(case.initial_state, predicate.initial_path)
    if initial is _MISSING:
        return False, "missing_initial_evidence"
    if not _is_number(value) or not _is_number(initial):
        return False, "non_numeric_comparison"
    return value > initial, "value_is_not_greater_than_initial"


def _less_than_initial(
    predicate: ArgumentPredicate, case: EvalCase, _: TrialTrace, value: object
) -> tuple[bool, str]:
    initial = _resolve_path(case.initial_state, predicate.initial_path)
    if initial is _MISSING:
        return False, "missing_initial_evidence"
    if not _is_number(value) or not _is_number(initial):
        return False, "non_numeric_comparison"
    return value < initial, "value_is_not_less_than_initial"


def _in_verified_context(
    _: ArgumentPredicate, __: EvalCase, trace: TrialTrace, value: object
) -> tuple[bool, str]:
    if not isinstance(value, str):
        return False, "context_id_is_not_a_string"
    return value in trace.verified_target_ids, "value_not_in_verified_context"


def _in_allowed_values(
    predicate: ArgumentPredicate, _: EvalCase, __: TrialTrace, value: object
) -> tuple[bool, str]:
    if not isinstance(predicate.expected, (tuple, list, frozenset, set)):
        return False, "expected_values_are_missing"
    return value in predicate.expected, "value_not_in_allowed_values"


def _target_is_active_radar(
    _: ArgumentPredicate, case: EvalCase, __: TrialTrace, value: object
) -> tuple[bool, str]:
    active_id = _resolve_path(case.initial_state, "/session/profile_id")
    if active_id is _MISSING:
        return False, "missing_active_radar_evidence"
    return value == active_id, "target_is_not_active_radar"


def _scope_equals(
    predicate: ArgumentPredicate, _: EvalCase, __: TrialTrace, value: object
) -> tuple[bool, str]:
    return value == predicate.expected, "scope_does_not_equal_expected"


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _failed(code: str, operator: str, detail: str) -> CheckResult:
    return CheckResult(code, False, operator == "target_is_active_radar", detail)


_EVALUATORS: Mapping[
    str, Callable[[ArgumentPredicate, EvalCase, TrialTrace, object], tuple[bool, str]]
] = {
    "equals": _equals,
    "greater_than_initial": _greater_than_initial,
    "less_than_initial": _less_than_initial,
    "in_verified_context": _in_verified_context,
    "in_allowed_values": _in_allowed_values,
    "target_is_active_radar": _target_is_active_radar,
    "scope_equals": _scope_equals,
}
