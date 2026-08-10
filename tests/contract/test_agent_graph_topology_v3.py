# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Graph topology v3 conformance: intent, clarification and HITL nodes (T017)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from langgraph.checkpoint.memory import MemorySaver

from tests.support.agent import RecordingRunRecorder
from tests.support.chat import RecordingConversation
from umbral.agent.graph import CHAT_TOPOLOGY_VERSION, build_topology_v3
from umbral.agent.intent.compiler import IntentCompiler
from umbral.agent.tools.executor import ToolExecutor
from umbral.agent.tools.registry import ToolRegistry
from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.tools.ports import SessionScope
from umbral.infrastructure.agent.intent.contract_loader import load_intent_contract
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract

ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY_CONTRACT = json.loads(
    (ROOT / "contracts" / "agent" / "v3" / "graph-topology-v3.json").read_text(
        encoding="utf-8"
    )
)

_REPLY_SCHEMA = {
    "reply_text": {"kind": "string"},
    "refs": {"kind": "list"},
    "tool_calls": {"kind": "list", "max_items": 5},
}


class _ScopeReader:
    def __init__(self, scope: SessionScope) -> None:
        self.scope = scope

    def read_scope(self, user_id: UUID, session_id: UUID) -> SessionScope | None:
        return self.scope


def _clock() -> datetime:
    return datetime.now(timezone.utc)


class _NoopDecisions:
    def get(self, **kwargs: object) -> object:
        raise AssertionError("decision gateway must not be called here")

    def reject(self, **kwargs: object) -> object:
        raise AssertionError("decision gateway must not be called here")

    def derive(self, **kwargs: object) -> object:
        raise AssertionError("decision gateway must not be called here")


class _FakeCompiler:
    def __init__(self, compilation: Mapping[str, object]) -> None:
        self._compilation = compilation

    def compile(self, **kwargs: object) -> object:
        return _CompilationResult(self._compilation)


class _CompilationResult:
    def __init__(self, data: Mapping[str, object]) -> None:
        self.intent = str(data.get("intent", ""))
        self.allowed_tools = tuple(data.get("allowed_tools", []))
        self.parameters = tuple(data.get("parameters", []))
        self.high_impact_missing = tuple(data.get("high_impact_missing", []))
        self.contradictions = tuple(data.get("contradictions", []))


def _build(compilation: Mapping[str, object]) -> object:
    recorder = RecordingRunRecorder()
    registry = ToolRegistry(load_tool_contract)
    scope = SessionScope(
        session_id=UUID(int=2), search_profile_id=UUID(int=5), status="active"
    )
    executor = ToolExecutor(
        registry=registry,
        implementations={},
        recorder=recorder,
        scope_reader=_ScopeReader(scope),
        timeout_seconds=1.0,
    )
    return build_topology_v3(
        gateway=_Gateway([{"reply_text": "ok", "refs": [], "tool_calls": []}]),
        conversation=RecordingConversation(),
        recorder=recorder,
        saver=MemorySaver(),
        tool_executor=executor,
        intent_compiler=_FakeCompiler(compilation),  # type: ignore[arg-type]
        decision_gateway=_NoopDecisions(),  # type: ignore[arg-type]
        clock=_clock,
        model_version="local-fake",
        prompt_version="agent-reply-v2",
        schema_version="reply-v3",
        reply_schema=_REPLY_SCHEMA,
        max_calls_per_turn=5,
        high_impact_keys=("budget", "zona", "hard_filters", "radio"),
        clarification_min_confidence=0.6,
        clarification_max_rounds=2,
        reply_chunk_words=8,
        reply_max_refs=10,
    )


def test_topology_v3_contract_declares_nodes_and_interrupts() -> None:
    assert TOPOLOGY_CONTRACT["contract_version"] == "3"
    assert TOPOLOGY_CONTRACT["registry_version"] == "agent-graph-topology-v3"
    assert TOPOLOGY_CONTRACT["topology_version"] == CHAT_TOPOLOGY_VERSION
    nodes = {node["name"] for node in TOPOLOGY_CONTRACT["nodes"]}
    assert nodes == {
        "start",
        "compile_intent",
        "clarify",
        "generate_reply",
        "run_tools",
        "require_confirmation",
        "resolve_decision",
        "persist_reply",
    }
    assert TOPOLOGY_CONTRACT["interrupts"][0]["name"] == "proposal_decision"


def test_built_graph_v3_matches_topology() -> None:
    graph = _build({"intent": "consulta", "allowed_tools": []})
    compiled = graph.compiled.get_graph()
    node_names = {node for node in compiled.nodes if not node.startswith("__")}
    assert node_names == {
        "start",
        "compile_intent",
        "clarify",
        "generate_reply",
        "run_tools",
        "require_confirmation",
        "resolve_decision",
        "persist_reply",
    }
    edges = {(edge.source, edge.target) for edge in compiled.edges}
    assert ("start", "compile_intent") in edges
    assert ("compile_intent", "clarify") in edges
    assert ("run_tools", "require_confirmation") in edges
    assert ("require_confirmation", "resolve_decision") in edges


class _Gateway:
    def __init__(self, replies: list[Mapping[str, object]]) -> None:
        self._replies = replies
        self.calls: list[Mapping[str, object]] = []

    def generate_structured(
        self,
        *,
        messages: tuple[Mapping[str, object], ...],
        schema: Mapping[str, object],
        schema_version: str,
        prompt_version: str,
        model_version: str,
    ) -> ModelResult:
        self.calls.append({"schema_version": schema_version})
        reply = self._replies[min(len(self.calls) - 1, len(self._replies) - 1)]
        return ModelResult(
            content=dict(reply),
            model_version="local-fake",
            status="success",
            latency_ms=1,
            input_tokens=8,
            output_tokens=16,
            total_tokens=24,
        )


def test_built_graph_v3_runs_consulta_turn_to_completion() -> None:
    graph = _build({"intent": "consulta", "allowed_tools": []})
    run_id = UUID(int=10)
    config = {"configurable": {"thread_id": str(run_id)}}
    state = {
        "schema_version": 3,
        "messages": [{"role": "user", "content": "qué criterios tengo?"}],
        "context": {
            "run_id": str(run_id),
            "session_id": str(UUID(int=2)),
            "user_id": str(UUID(int=3)),
            "correlation_id": str(UUID(int=4)),
            "user_message_text": "qué criterios tengo?",
            "effects_applied": {},
            "token_usage": {"input": 0, "output": 0, "total": 0},
        },
        "intent": None,
        "clarification": None,
        "pending_action": None,
        "tool_calls": [],
        "tool_results": [],
        "errors": [],
    }
    list(graph.compiled.stream(state, config, stream_mode="updates"))
    final = graph.compiled.get_state(config).values
    assert final["errors"] == []
    assert final["intent"]["intent"] == "consulta"
    assert final["tool_calls"] == []
