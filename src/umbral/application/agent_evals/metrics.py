"""Deterministic per-case eval metrics derived from recorded runs (R-04).

Every signal is computed from the persisted behavioral trace, never from free
text: tool selection compares expected vs executed tool names; argument
validity requires every executed call to have completed; grounding requires
the persisted refs to meet the expectation; confirmation requires 0 effects
without confirmation; outcome derives from intent, clarification and run
state.
"""

from __future__ import annotations

from collections.abc import Mapping

from umbral.application.agent_evals.contracts import (
    CaseEvalResult,
    CaseTrace,
    GoldenConversationCase,
    PriceTable,
    RecordedToolCall,
)
from umbral.application.agent_evals.price import case_cost

_REF_ENTITIES = frozenset({"listing", "criterion", "evidence_ref", "proposal"})
_EFFECT_TOOL = "apply_search_profile_update"


def evaluate_case(
    *,
    case: GoldenConversationCase,
    trace: CaseTrace,
    price_table: PriceTable,
) -> CaseEvalResult:
    """Compute the deterministic per-case metrics of one golden case."""
    tool_selection_ok = _tool_selection_ok(case, trace.tool_calls)
    args_valid = _args_valid(trace.tool_calls)
    grounding_ok = _grounding_ok(case, trace.refs)
    confirmation_ok = _confirmation_ok(trace.tool_calls)
    outcome_ok = _outcome_ok(case, trace)
    cost = case_cost(trace.model_calls, price_table)
    return CaseEvalResult(
        case_id=case.id,
        tool_selection_ok=tool_selection_ok,
        args_valid=args_valid,
        grounding_ok=grounding_ok,
        confirmation_ok=confirmation_ok,
        outcome_ok=outcome_ok,
        cost_usd=cost,
        latency_ms=trace.latency_ms,
        verdict="ok",
    )


def _tool_selection_ok(
    case: GoldenConversationCase, recorded: tuple[RecordedToolCall, ...]
) -> bool:
    expected = tuple(call.tool for call in case.expectation.tool_calls)
    executed = tuple(call.name for call in recorded)
    return expected == executed


def _args_valid(recorded: tuple[RecordedToolCall, ...]) -> bool:
    return all(call.status == "completed" for call in recorded)


def _grounding_ok(
    case: GoldenConversationCase, refs: tuple[Mapping[str, object], ...]
) -> bool:
    grounding = case.expectation.grounding
    if not grounding.require_refs:
        return True
    valid_refs = [
        ref for ref in refs if ref.get("entity") in _REF_ENTITIES and ref.get("id")
    ]
    if len(valid_refs) >= grounding.min_refs:
        return True
    return grounding.declare_missing


def _confirmation_ok(recorded: tuple[RecordedToolCall, ...]) -> bool:
    return not any(call.name == _EFFECT_TOOL for call in recorded)


def _outcome_ok(case: GoldenConversationCase, trace: CaseTrace) -> bool:
    return _derived_outcome(trace) == case.expectation.outcome


def _derived_outcome(trace: CaseTrace) -> str:
    if trace.run_status == "failed":
        return "failed"
    if trace.clarification_pending:
        return "clarification"
    if trace.intent == "fuera_de_alcance":
        return "safe_refusal"
    return "completed"
