"""Unit tests for the separate V5 conversation graph."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from umbral.agent.graph_v5 import (
    ConversationGraphStateV5,
    GraphDepsV5,
    build_graph_v5,
)
from umbral.application.conversation.v5.contracts import (
    ActOutcomeV5,
    ConceptLinkV5,
    ConversationTurnResultV5,
    EvidenceSpan,
    ExecutedActV5,
    ExpressDesire,
    PendingActionV5,
    Query,
    RecordDesireCommand,
    TurnContextV5,
    TurnInterpretationV5,
    TurnPlanV5,
)
from umbral.application.conversation.v5.reply import ReplyOutcomeV5, ReplyV5

ROOT = Path(__file__).resolve().parents[3]
TOPOLOGY = json.loads(
    (ROOT / "contracts" / "agent" / "v5" / "graph-topology-v5.json").read_text(
        encoding="utf-8"
    )
)

USER_ID = UUID(int=1)
SESSION_ID = UUID(int=2)
CORRELATION_ID = UUID(int=3)


def _context() -> TurnContextV5:
    return TurnContextV5(
        user_id=str(USER_ID),
        session_id=str(SESSION_ID),
        active_radar_ref="radar:1",
        active_radar_version=1,
        current_filters=(),
        active_desires=(),
        pending_action=None,
        focused_entity=None,
        verified_listing_refs=(),
        allowed_capabilities=("express_desire", "query"),
        untrusted_content=(),
        context_schema_version="5",
        correlation_id=str(CORRELATION_ID),
    )


def _interpretation() -> TurnInterpretationV5:
    return TurnInterpretationV5(
        model_version="gpt-4.1-mini",
        prompt_version="interpretation-v5",
        acts=(
            ExpressDesire(
                act_id="a1",
                confidence=0.9,
                evidence_spans=(EvidenceSpan(start=0, end=11, text="quiero balcón"),),
                raw_text="quiero balcón",
                subject_ref="balcon",
                concept_links=(
                    ConceptLinkV5(
                        concept_ref="balcon",
                        confidence=0.9,
                        polarity="positive",
                        intensity="high",
                    ),
                ),
            ),
        ),
    )


def _plan() -> TurnPlanV5:
    return TurnPlanV5(
        decisions=(),
        commands=(
            RecordDesireCommand(
                act_id="a1",
                raw_text="quiero balcón",
                subject_ref="balcon",
                concept_links=(
                    ConceptLinkV5(
                        concept_ref="balcon",
                        confidence=0.9,
                        polarity="positive",
                        intensity="high",
                    ),
                ),
            ),
        ),
    )


class _FakeTurn:
    def __init__(
        self,
        result: ConversationTurnResultV5,
        result_after_resume: ConversationTurnResultV5 | None = None,
        resolved_context: TurnContextV5 | None = None,
    ) -> None:
        self.result = result
        self.result_after_resume = result_after_resume or result
        self.resolved_context = resolved_context
        self.execute_calls = 0
        self.load_calls = 0
        self.plans: list[TurnPlanV5] = []
        self.resolutions: list[tuple[str, str]] = []

    def load_context(
        self, *, user_id: UUID, session_id: UUID, correlation_id: UUID
    ) -> TurnContextV5:
        self.load_calls += 1
        if self.resolutions:
            return self.resolved_context or _context()
        if self.execute_calls and self.result.context.pending_action is not None:
            return self.result.context
        return _context()

    def interpret(
        self,
        *,
        message_text: str,
        context: TurnContextV5,
        correlation_id: UUID,
    ) -> TurnInterpretationV5:
        return _interpretation()

    def plan(
        self,
        *,
        user_message: str,
        context: TurnContextV5,
        interpretation: TurnInterpretationV5,
    ) -> TurnPlanV5:
        return _plan()

    def execute(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        message_id: UUID,
        message_text: str,
        correlation_id: UUID,
        context: TurnContextV5,
        interpretation: TurnInterpretationV5,
        plan: TurnPlanV5,
    ) -> ConversationTurnResultV5:
        self.execute_calls += 1
        self.plans.append(plan)
        if self.execute_calls == 1:
            return self.result
        return self.result_after_resume

    def resolve_pending(
        self, *, act_id: str, context: TurnContextV5, pending_ref: str,
        decision: str, correlation_id: UUID, idempotency_key: str,
    ) -> object:
        self.resolutions.append((pending_ref, decision))
        return ExecutedActV5(
            act_id=act_id,
            effect_key="pending.resolved",
            status="rejected" if decision == "reject" else "applied",
            reason_code="user" if decision == "reject" else None,
        )


class _FakeReply:
    def __init__(self, reply: ReplyV5) -> None:
        self.reply = reply
        self.results: list[ConversationTurnResultV5] = []

    def compose(self, result: ConversationTurnResultV5) -> ReplyV5:
        self.results.append(result)
        return self.reply


def _applied_result() -> ConversationTurnResultV5:
    return ConversationTurnResultV5(
        context=_context(),
        interpretation=_interpretation(),
        plan=_plan(),
        executed=(),
        outcomes=(ActOutcomeV5("a1", "applied"),),
        failure_stage=None,
    )


def _pending_result() -> ConversationTurnResultV5:
    return ConversationTurnResultV5(
        context=replace(
            _context(),
            pending_action=PendingActionV5(
                pending_ref="pending:head", act_id="a1", ordinal=1, total=1
            ),
        ),
        interpretation=_interpretation(),
        plan=_plan(),
        executed=(),
        outcomes=(
            ActOutcomeV5(
                "a1",
                "pending",
                reason_code="filter.changes_existing_hard_filter",
                object_ref=f"proposal:{uuid4()}",
            ),
        ),
        failure_stage=None,
    )


def _reply() -> ReplyV5:
    return ReplyV5(
        text="Listo.",
        outcomes=(ReplyOutcomeV5("a1", "applied"),),
        verified_refs=(),
        source="managed",
    )


def _graph(turn: _FakeTurn, reply: _FakeReply | None = None) -> Any:
    deps = GraphDepsV5(turn=turn, reply=reply or _FakeReply(_reply()))
    return build_graph_v5(dependencies=deps, checkpointer=MemorySaver())


def _config() -> dict[str, object]:
    return {
        "configurable": {
            "thread_id": "thread-1",
            "user_id": str(USER_ID),
            "session_id": str(SESSION_ID),
            "correlation_id": str(CORRELATION_ID),
        }
    }


def _state(message: str = "quiero balcón") -> ConversationGraphStateV5:
    return {
        "contract_version": "5",
        "schema_version": "conversation-state-v5",
        "message_id": str(UUID(int=4)),
        "message_text": message,
    }


def test_graph_matches_published_topology() -> None:
    graph = _graph(_FakeTurn(_applied_result()))
    compiled = graph.get_graph()

    published = TOPOLOGY["examples"][0]
    published_nodes = {node["name"] for node in published["nodes"]}
    node_names = {node for node in compiled.nodes if not node.startswith("__")}
    assert node_names == published_nodes - {"end"}

    edges = {(edge.source, edge.target) for edge in compiled.edges}
    for source, target in (
        (edge["from"], edge["to"]) for edge in published["edges"]
    ):
        if target == "end":
            assert (source, "__end__") in edges
        elif source == "end":
            continue
        else:
            assert (source, target) in edges
    assert ("persist_turn", "__end__") in edges
    # Interpretation never routes directly to execution.
    assert ("interpret_turn", "execute_segment") not in edges
    # The interrupt is declared in the published topology.
    assert TOPOLOGY["examples"][0]["interrupts"] == ["confirmation"]


def test_graph_runs_a_full_turn_and_produces_reply() -> None:
    turn = _FakeTurn(_applied_result())
    graph = _graph(turn)

    final = graph.invoke(_state(), _config())

    assert final["reply"] is not None
    assert final["reply"]["source"] == "managed"
    assert final["outcomes"][0]["status"] == "applied"
    assert turn.execute_calls == 1
    concept_link = final["interpretation"]["acts"][0]["concept_links"][0]
    assert concept_link["polarity"] == "positive"
    assert concept_link["intensity"] == "high"
    command_link = turn.plans[0].commands[0].concept_links[0]
    assert command_link.polarity == "positive"
    assert command_link.intensity == "high"


def test_graph_interrupts_on_pending_and_resumes() -> None:
    turn = _FakeTurn(_pending_result(), _applied_result())
    graph = _graph(turn)

    first = graph.invoke(_state(), _config())
    assert first["reply"] is not None
    assert first["outcomes"][0]["status"] == "pending"

    resumed = graph.invoke(
        Command(resume={"decision": "approve"}), _config()
    )
    assert resumed.get("confirmation_payload") is not None
    assert resumed["reply"] is not None
    assert turn.execute_calls == 1


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_graph_composes_resolution_before_the_next_confirmation(
    decision: str,
) -> None:
    first_head = PendingActionV5(
        pending_ref="pending:zones", act_id="zones", ordinal=1, total=2
    )
    next_head = PendingActionV5(
        pending_ref="pending:budget", act_id="budget", ordinal=2, total=2
    )
    initial = _pending_result()
    initial = ConversationTurnResultV5(
        context=replace(_context(), pending_action=first_head),
        interpretation=initial.interpretation,
        plan=initial.plan,
        executed=initial.executed,
        outcomes=initial.outcomes,
    )
    reply = _FakeReply(_reply())
    turn = _FakeTurn(
        initial,
        resolved_context=replace(_context(), pending_action=next_head),
    )
    graph = _graph(turn, reply)

    graph.invoke(_state(), _config())
    resumed = graph.invoke(Command(resume={"decision": decision}), _config())

    assert resumed["reply"] is not None
    assert reply.results[-1].context.pending_action == next_head
    assert reply.results[-1].outcomes[-1].status == (
        "applied" if decision == "approve" else "rejected"
    )


def test_graph_does_not_interrupt_pure_query_for_an_existing_queue() -> None:
    pending = PendingActionV5(
        pending_ref="pending:zones", act_id="zones", ordinal=1, total=2
    )
    query = Query(
        act_id="query",
        confidence=1,
        evidence_spans=(EvidenceSpan(0, 13, "mostrá opciones"),),
        query_text="mostrá opciones",
    )
    result = ConversationTurnResultV5(
        context=replace(_context(), pending_action=pending),
        interpretation=TurnInterpretationV5(
            model_version="test", prompt_version="test", acts=(query,)
        ),
        plan=TurnPlanV5(decisions=()),
        executed=(),
        outcomes=(ActOutcomeV5("query", "applied"),),
    )
    graph = _graph(_FakeTurn(result))

    updates = tuple(
        graph.stream(_state("mostrá opciones"), _config(), stream_mode="updates")
    )

    assert not any("__interrupt__" in update for update in updates)


def test_graph_resume_resolves_only_the_context_queue_head() -> None:
    pending = PendingActionV5(
        pending_ref="pending:head", act_id="zones", ordinal=1, total=2
    )
    result = _pending_result()
    result = ConversationTurnResultV5(
        context=replace(_context(), pending_action=pending),
        interpretation=result.interpretation, plan=result.plan,
        executed=result.executed, outcomes=result.outcomes,
    )
    turn = _FakeTurn(result, _applied_result())
    graph = _graph(turn)

    graph.invoke(_state(), _config())
    resumed = graph.invoke(Command(resume={"decision": "reject"}), _config())

    assert turn.resolutions == [("pending:head", "reject")]
    assert resumed["outcomes"][-1]["status"] == "rejected"
    assert resumed["outcomes"][-1]["reason_code"] == "user"
