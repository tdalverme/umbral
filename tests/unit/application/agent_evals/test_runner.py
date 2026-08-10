"""Unit tests of the pure suite runner (T017)."""

from __future__ import annotations

from umbral.application.agent_evals.contracts import (
    CaseTrace,
    GoldenConversationCase,
    GraphRelease,
    ModelCallCostRecord,
    PriceTable,
    PriceTableEntry,
    RecordedToolCall,
)
from umbral.application.agent_evals.runner import run_suite

_TABLE = PriceTable(
    contract_version="1",
    registry_version="price-table-v1",
    currency="usd",
    entries=(
        PriceTableEntry(model_version="provider-x-model-y", price_input_per_1k=0.0005, price_output_per_1k=0.0015),
    ),
)


class _FakeDataset:
    def __init__(self, cases: tuple[GoldenConversationCase, ...]) -> None:
        self.registry_version = "conversations-golden-v1"
        self.cases = cases


class _FakeExecutor:
    def __init__(self, trace: CaseTrace) -> None:
        self.trace = trace

    def execute(self, *, case: GoldenConversationCase, release: GraphRelease) -> CaseTrace:
        return CaseTrace(
            case_id=case.id,
            run_status=self.trace.run_status,
            intent=self.trace.intent,
            clarification_pending=self.trace.clarification_pending,
            tool_calls=self.trace.tool_calls,
            model_calls=self.trace.model_calls,
            latency_ms=self.trace.latency_ms,
            refs=self.trace.refs,
        )


def _case(case_id: str) -> GoldenConversationCase:
    from umbral.application.agent_evals.contracts import (
        GoldenExpectation,
        GroundingExpectation,
    )

    return GoldenConversationCase(
        id=case_id,
        family="onboarding",
        context={"profile": {"budget_max": 900000, "zone": "palermo"}},
        turns=("hola",),
        expectation=GoldenExpectation(
            tool_calls=(),
            grounding=GroundingExpectation(require_refs=False, min_refs=0, declare_missing=False),
            outcome="completed",
        ),
    )


def test_run_suite_evaluates_every_case_with_the_executor() -> None:
    cases = (_case("conversation-001"), _case("conversation-002"))
    executor = _FakeExecutor(
        CaseTrace(
            case_id="",
            run_status="completed",
            intent="consulta",
            clarification_pending=False,
            tool_calls=(RecordedToolCall(name="get_search_profile", status="completed"),),
            model_calls=(ModelCallCostRecord(model_version="provider-x-model-y", input_tokens=8, output_tokens=16),),
            latency_ms=4,
            refs=(),
        )
    )
    release = _release()
    results = run_suite(
        executor=executor,
        dataset=_FakeDataset(cases),
        release=release,
        price_table=_TABLE,
    )
    assert len(results) == 2
    assert {item.case_id for item in results} == {"conversation-001", "conversation-002"}
    assert all(item.latency_ms == 4 for item in results)


def _release() -> GraphRelease:
    from umbral.application.agent_evals.contracts import (
        ReleaseActivation,
        ReleaseComponents,
    )

    return GraphRelease(
        id="graph-release-001",
        components=ReleaseComponents(
            prompt_versions=("agent-intent-v1", "agent-reply-v2"),
            model_version="provider-x-model-y",
            state_schema_version="chat-state-v3",
            topology_version="chat-topology-v3",
            intent_schema_version="intent-schema-v3",
            price_table_version="price-table-v1",
            touches_prompts_or_model=False,
        ),
        owner="team-agent",
        justification="release inicial",
        affected_case_ids=(),
        activation=ReleaseActivation(
            status="active", approved_by=None, approval_evidence=None, reverted_reason=None
        ),
        date="2026-08-10",
    )
