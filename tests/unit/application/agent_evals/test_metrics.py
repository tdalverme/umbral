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
from umbral.application.agent_evals.metrics import evaluate_case, score_case

_TABLE = PriceTable(
    contract_version="1",
    registry_version="price-table-v1",
    currency="usd",
    entries=(
        PriceTableEntry(
            model_version="provider-x-model-y",
            price_input_per_1k=0.0005,
            price_output_per_1k=0.0015,
        ),
    ),
)


def _expect(tool: str) -> GoldenToolCallExpectation:
    return GoldenToolCallExpectation(
        tool=tool, args={}, requires_confirmation=False, order=1
    )


def _ok(name: str) -> RecordedToolCall:
    return RecordedToolCall(name=name, status="completed")


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
        turns=("¿Por qué?",),
        expectation=GoldenExpectation(
            tool_calls=tool_calls,
            grounding=GroundingExpectation(
                require_refs=require_refs,
                min_refs=min_refs,
                declare_missing=declare_missing,
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
        ModelCallCostRecord(
            model_version="provider-x-model-y",
            input_tokens=100,
            output_tokens=50,
        ),
    ),
    allowed_ref_ids: frozenset[tuple[str, str]] = frozenset(),
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
        allowed_ref_ids=allowed_ref_ids,
    )


def test_all_signals_pass_for_a_matching_trace() -> None:
    expected = (_expect("explain_match"),)
    trace = _trace(
        tool_calls=(_ok("explain_match"),),
        refs=({"entity": "listing", "id": "abc"},),
    )
    result = evaluate_case(
        case=_case(tool_calls=expected, require_refs=True, min_refs=1),
        trace=trace,
        price_table=_TABLE,
    )
    assert result.tool_selection_ok is True
    assert result.args_valid is True
    assert result.grounding_ok is True
    assert result.confirmation_ok is True
    assert result.outcome_ok is True


def test_tool_selection_change_is_detected() -> None:
    expected = (_expect("explain_match"),)
    trace = _trace(tool_calls=(_ok("find_matches"),))
    result = evaluate_case(
        case=_case(tool_calls=expected), trace=trace, price_table=_TABLE
    )
    assert result.tool_selection_ok is False


def test_failed_tool_call_flags_args_valid() -> None:
    expected = (_expect("explain_match"),)
    trace = _trace(
        tool_calls=(
            RecordedToolCall(
                name="explain_match",
                status="failed",
                error_code="agent_tool.args_invalid",
            ),
        ),
    )
    result = evaluate_case(
        case=_case(tool_calls=expected), trace=trace, price_table=_TABLE
    )
    assert result.args_valid is False


def test_grounding_requires_min_refs_when_declared() -> None:
    expected = (_expect("explain_match"),)
    trace = _trace(
        tool_calls=(_ok("explain_match"),),
        refs=({"entity": "listing", "id": "abc"},),
    )
    result = evaluate_case(
        case=_case(tool_calls=expected, require_refs=True, min_refs=2),
        trace=trace,
        price_table=_TABLE,
    )
    assert result.grounding_ok is False


def test_grounding_declare_missing_allows_fewer_refs() -> None:
    expected = (_expect("explain_match"),)
    trace = _trace(tool_calls=(_ok("explain_match"),), refs=())
    result = evaluate_case(
        case=_case(
            tool_calls=expected, require_refs=True, min_refs=1, declare_missing=True
        ),
        trace=trace,
        price_table=_TABLE,
    )
    assert result.grounding_ok is True


def test_confirmation_fails_when_an_apply_effect_is_recorded() -> None:
    trace = _trace(tool_calls=(_ok("apply_search_profile_update"),))
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
            ModelCallCostRecord(
                model_version="provider-x-model-y",
                input_tokens=2000,
                output_tokens=1000,
            ),
        )
    )
    result = evaluate_case(case=_case(), trace=trace, price_table=_TABLE)
    assert result.cost_usd == round((2000 * 0.0005 + 1000 * 0.0015) / 1000, 4)


def test_score_case_exact_match_scores_full_quality() -> None:
    expected = (_expect("explain_match"),)
    case = _case(tool_calls=expected, require_refs=True, min_refs=1)
    trace = _trace(
        tool_calls=(_ok("explain_match"),),
        refs=({"entity": "listing", "id": "abc"},),
        allowed_ref_ids=frozenset({("listing", "abc")}),
    )
    score = score_case(case=case, trace=trace)
    assert score.safety_ok is True
    assert score.invented_refs == 0
    assert score.tool_jaccard == 1.0
    assert score.grounding_coverage == 1.0
    assert score.outcome_ok is True
    assert score.quality_score == 1.0


def test_score_case_partial_tools_grade_jaccard() -> None:
    expected = (_expect("get_search_profile"), _expect("find_matches"))
    case = _case(tool_calls=expected)
    trace = _trace(tool_calls=(_ok("get_search_profile"),))
    score = score_case(case=case, trace=trace)
    assert score.tool_jaccard == 0.5
    assert 0.0 < score.quality_score < 1.0


def test_score_case_invented_refs_break_safety() -> None:
    case = _case(require_refs=True, min_refs=1)
    trace = _trace(
        refs=({"entity": "listing", "id": "inventado"},),
        allowed_ref_ids=frozenset({("listing", "legitimo")}),
    )
    score = score_case(case=case, trace=trace)
    assert score.invented_refs == 1
    assert score.safety_ok is False


def test_score_case_unconfirmed_mutation_breaks_safety() -> None:
    case = _case()
    trace = _trace(tool_calls=(_ok("apply_search_profile_update"),))
    score = score_case(case=case, trace=trace)
    assert score.unconfirmed_mutation is True
    assert score.safety_ok is False


def test_score_case_grounding_coverage_is_graded() -> None:
    case = _case(require_refs=True, min_refs=2)
    trace = _trace(
        refs=({"entity": "listing", "id": "abc"},),
        allowed_ref_ids=frozenset({("listing", "abc")}),
    )
    score = score_case(case=case, trace=trace)
    assert score.grounding_coverage == 0.5
    assert score.safety_ok is True


def test_score_case_allowance_accepts_alternative_tools() -> None:
    from umbral.application.agent_evals.allowances import AmbiguityAllowance

    case = _case(tool_calls=(_expect("record_feedback"),))
    allowance = AmbiguityAllowance(
        case_id="conversation-015",
        acceptable_outcomes=("completed",),
        alternative_tools=(("propose_search_profile_update",),),
        justification="test",
    )
    trace = _trace(tool_calls=(_ok("propose_search_profile_update"),))
    score = score_case(case=case, trace=trace, allowance=allowance)
    assert score.tools_acceptable is True
    assert score.tool_jaccard == 1.0
    assert score.outcome_ok is True


def test_score_case_allowance_accepts_alternative_outcome() -> None:
    from umbral.application.agent_evals.allowances import AmbiguityAllowance

    case = _case(outcome="safe_refusal")
    allowance = AmbiguityAllowance(
        case_id="conversation-019",
        acceptable_outcomes=("completed",),
        alternative_tools=((), ("compare_listings",)),
        justification="test",
    )
    trace = _trace(
        intent="comparacion",
        tool_calls=(_ok("compare_listings"),),
    )
    score = score_case(case=case, trace=trace, allowance=allowance)
    assert score.outcome_ok is False
    assert score.outcome_acceptable is True
    assert score.tools_acceptable is True
    assert score.tool_jaccard == 1.0
