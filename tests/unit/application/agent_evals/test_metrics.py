"""Unit tests of the deterministic per-case metrics (T016)."""

from __future__ import annotations

from umbral.application.agent_evals.contracts import (
    CaseTrace,
    GoldenConversationCase,
    GoldenExpectation,
    GoldenToolCallExpectation,
    GroundingExpectation,
    ModelCallCostRecord,
    PriceTable,
    PriceTableEntry,
    RecordedToolCall,
)
from umbral.application.agent_evals.metrics import evaluate_case

_TABLE = PriceTable(
    contract_version="1",
    registry_version="price-table-v1",
    currency="usd",
    entries=(
        PriceTableEntry(model_version="provider-x-model-y", price_input_per_1k=0.0005, price_output_per_1k=0.0015),
    ),
)


def _case(
    *,
    tool_calls: tuple[GoldenToolCallExpectation, ...] = (),
    require_refs: bool = False,
    min_refs: int = 0,
    declare_missing: bool = False,
    outcome: str = "completed",
) -> GoldenConversationCase:
    return GoldenConversationCase(
        id="conversation-001",
        family="explanation",
        context={"profile": {"budget_max": 900000, "zone": "palermo"}},
        turns=("¿Por qué?"),
        expectation=GoldenExpectation(
            tool_calls=tool_calls,
            grounding=GroundingExpectation(
                require_refs=require_refs, min_refs=min_refs, declare_missing=declare_missing
            ),
            outcome=outcome,  # type: ignore[arg-type]
        ),
    )


def _trace(
    *,
    tool_calls: tuple[RecordedToolCall, ...] = (),
    run_status: str = "completed",
    intent: str | None = "consulta",
    clarification_pending: bool = False,
    refs: tuple[dict[str, object], ...] = (),
    latency_ms: int = 10,
    model_calls: tuple[ModelCallCostRecord, ...] = (
        ModelCallCostRecord(model_version="provider-x-model-y", input_tokens=100, output_tokens=50),
    ),
) -> CaseTrace:
    return CaseTrace(
        case_id="conversation-001",
        run_status=run_status,
        intent=intent,
        clarification_pending=clarification_pending,
        tool_calls=tool_calls,
        model_calls=model_calls,
        latency_ms=latency_ms,
        refs=refs,
    )


def test_all_signals_pass_for_a_matching_trace() -> None:
    expected = (
        GoldenToolCallExpectation(tool="explain_match", args={}, requires_confirmation=False, order=1),
    )
    trace = _trace(
        tool_calls=(RecordedToolCall(name="explain_match", status="completed"),),
        refs=({"entity": "listing", "id": "abc"},),
    )
    result = evaluate_case(case=_case(tool_calls=expected, require_refs=True, min_refs=1), trace=trace, price_table=_TABLE)
    assert result.tool_selection_ok is True
    assert result.args_valid is True
    assert result.grounding_ok is True
    assert result.confirmation_ok is True
    assert result.outcome_ok is True


def test_tool_selection_change_is_detected() -> None:
    expected = (GoldenToolCallExpectation(tool="explain_match", args={}, requires_confirmation=False, order=1),)
    trace = _trace(tool_calls=(RecordedToolCall(name="find_matches", status="completed"),))
    result = evaluate_case(case=_case(tool_calls=expected), trace=trace, price_table=_TABLE)
    assert result.tool_selection_ok is False


def test_failed_tool_call_flags_args_valid() -> None:
    expected = (GoldenToolCallExpectation(tool="explain_match", args={}, requires_confirmation=False, order=1),)
    trace = _trace(tool_calls=(RecordedToolCall(name="explain_match", status="failed", error_code="agent_tool.args_invalid"),))
    result = evaluate_case(case=_case(tool_calls=expected), trace=trace, price_table=_TABLE)
    assert result.args_valid is False


def test_grounding_requires_min_refs_when_declared() -> None:
    expected = (GoldenToolCallExpectation(tool="explain_match", args={}, requires_confirmation=False, order=1),)
    trace = _trace(
        tool_calls=(RecordedToolCall(name="explain_match", status="completed"),),
        refs=({"entity": "listing", "id": "abc"},),
    )
    result = evaluate_case(
        case=_case(tool_calls=expected, require_refs=True, min_refs=2),
        trace=trace,
        price_table=_TABLE,
    )
    assert result.grounding_ok is False


def test_grounding_declare_missing_allows_fewer_refs() -> None:
    expected = (GoldenToolCallExpectation(tool="explain_match", args={}, requires_confirmation=False, order=1),)
    trace = _trace(
        tool_calls=(RecordedToolCall(name="explain_match", status="completed"),),
        refs=(),
    )
    result = evaluate_case(
        case=_case(tool_calls=expected, require_refs=True, min_refs=1, declare_missing=True),
        trace=trace,
        price_table=_TABLE,
    )
    assert result.grounding_ok is True


def test_confirmation_fails_when_an_apply_effect_is_recorded() -> None:
    trace = _trace(tool_calls=(RecordedToolCall(name="apply_search_profile_update", status="completed"),))
    result = evaluate_case(case=_case(), trace=trace, price_table=_TABLE)
    assert result.confirmation_ok is False


def test_outcome_matches_intent_and_clarification() -> None:
    assert evaluate_case(
        case=_case(outcome="clarification"),
        trace=_trace(intent="refinamiento", clarification_pending=True),
        price_table=_TABLE,
    ).outcome_ok is True
    assert evaluate_case(
        case=_case(outcome="safe_refusal"),
        trace=_trace(intent="fuera_de_alcance"),
        price_table=_TABLE,
    ).outcome_ok is True
    assert evaluate_case(
        case=_case(outcome="completed"),
        trace=_trace(run_status="failed"),
        price_table=_TABLE,
    ).outcome_ok is False


def test_cost_is_derived_from_tokens() -> None:
    trace = _trace(
        model_calls=(
            ModelCallCostRecord(model_version="provider-x-model-y", input_tokens=2000, output_tokens=1000),
        )
    )
    result = evaluate_case(case=_case(), trace=trace, price_table=_TABLE)
    assert result.cost_usd == round((2000 * 0.0005 + 1000 * 0.0015) / 1000, 4)
