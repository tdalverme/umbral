# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Graph topology v2 conformance: bounded tool loop (R-14, T015)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from langgraph.checkpoint.memory import MemorySaver

from tests.support.agent import RecordingRunRecorder
from tests.support.chat import RecordingConversation
from umbral.agent.graph import TOOLS_TOPOLOGY_VERSION, build_topology_v2
from umbral.agent.tools.executor import ToolExecutor
from umbral.agent.tools.registry import ToolRegistry
from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.tools.ports import SessionScope
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract

ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY_CONTRACT = json.loads(
    (ROOT / "contracts" / "agent" / "v2" / "graph-topology-v2.json").read_text(
        encoding="utf-8"
    )
)

_REPLY_SCHEMA = {
    "reply_text": {"kind": "string"},
    "refs": {"kind": "list"},
    "tool_calls": {"kind": "list", "max_items": 5},
}

TOOL_NAMES = {
    "get_search_profile",
    "propose_search_profile_update",
    "apply_search_profile_update",
    "find_matches",
    "explain_match",
    "compare_listings",
    "record_feedback",
    "search_urban_context",
}


class _ScopeReader:
    def __init__(self, scope: SessionScope) -> None:
        self.scope = scope

    def read_scope(self, user_id: UUID, session_id: UUID) -> SessionScope | None:
        return self.scope


def _clock() -> datetime:
    return datetime.now(timezone.utc)


def _executor(recorder: RecordingRunRecorder, registry: ToolRegistry) -> ToolExecutor:
    scope = SessionScope(
        session_id=UUID(int=2),
        search_profile_id=UUID(int=5),
        status="active",
    )
    return ToolExecutor(
        registry=registry,
        implementations={},
        recorder=recorder,
        scope_reader=_ScopeReader(scope),
        timeout_seconds=1.0,
    )


class _ScriptedGateway:
    """Returns a scripted sequence of structured replies (with tool_calls)."""

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
        tools: Sequence[Mapping[str, object]] | None = None,
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


def test_topology_v2_contract_declares_tools_and_loop() -> None:
    assert TOPOLOGY_CONTRACT["contract_version"] == "2"
    assert TOPOLOGY_CONTRACT["registry_version"] == "agent-graph-topology-v2"
    assert TOPOLOGY_CONTRACT["topology_version"] == TOOLS_TOPOLOGY_VERSION
    assert TOPOLOGY_CONTRACT["entry"] == "start"
    nodes = {node["name"] for node in TOPOLOGY_CONTRACT["nodes"]}
    assert nodes == {"start", "generate_reply", "run_tools", "persist_reply"}
    assert set(TOPOLOGY_CONTRACT["tools"]) == TOOL_NAMES
    assert TOPOLOGY_CONTRACT["interrupts"] == []


def test_built_graph_v2_matches_topology() -> None:
    recorder = RecordingRunRecorder()
    registry = ToolRegistry(load_tool_contract)
    graph = build_topology_v2(
        gateway=_ScriptedGateway(
            [
                {"reply_text": "llamando", "refs": [], "tool_calls": []},
            ]
        ),
        conversation=RecordingConversation(),
        recorder=recorder,
        saver=MemorySaver(),
        tool_executor=_executor(recorder, registry),
        clock=_clock,
        model_version="local-fake",
        prompt_version="agent-tools-v1",
        schema_version="reply-v2",
        reply_schema=_REPLY_SCHEMA,
        max_calls_per_turn=5,
    )
    compiled = graph.compiled.get_graph()
    node_names = {node for node in compiled.nodes if not node.startswith("__")}
    assert node_names == {"start", "generate_reply", "run_tools", "persist_reply"}
    edges = {(edge.source, edge.target) for edge in compiled.edges}
    assert ("start", "generate_reply") in edges
    assert ("generate_reply", "run_tools") in edges
    assert ("run_tools", "generate_reply") in edges
    assert ("persist_reply", "__end__") in edges


def test_built_graph_v2_executes_tool_calls_and_loops() -> None:
    recorder = RecordingRunRecorder()
    registry = ToolRegistry(load_tool_contract)

    def find_matches(_ctx, args):
        return {"run_id": None, "items": [], "total": 0, "stale": True}

    executor = ToolExecutor(
        registry=registry,
        implementations={"find_matches": find_matches},
        recorder=recorder,
        scope_reader=_ScopeReader(
            SessionScope(
                session_id=UUID(int=2),
                search_profile_id=UUID(int=5),
                status="active",
            )
        ),
        timeout_seconds=1.0,
    )
    gateway = _ScriptedGateway(
        [
            {
                "reply_text": "busco",
                "refs": [],
                "tool_calls": [
                    {"tool": "find_matches", "args": {"page": 1, "limit": 5}}
                ],
            },
            {"reply_text": "no hay resultados", "refs": [], "tool_calls": []},
        ]
    )
    graph = build_topology_v2(
        gateway=gateway,
        conversation=RecordingConversation(),
        recorder=recorder,
        saver=MemorySaver(),
        tool_executor=executor,
        clock=_clock,
        model_version="local-fake",
        prompt_version="agent-tools-v1",
        schema_version="reply-v2",
        reply_schema=_REPLY_SCHEMA,
        max_calls_per_turn=5,
    )
    run_id = UUID(int=10)
    config = {"configurable": {"thread_id": str(run_id)}}
    state = {
        "schema_version": 2,
        "messages": [{"role": "user", "content": "mostrame"}],
        "context": {
            "run_id": str(run_id),
            "session_id": str(UUID(int=2)),
            "user_id": str(UUID(int=3)),
            "correlation_id": str(UUID(int=4)),
            "user_message_text": "mostrame",
            "effects_applied": {},
            "token_usage": {"input": 0, "output": 0, "total": 0},
        },
        "intent": None,
        "pending_action": None,
        "tool_calls": [],
        "tool_results": [],
        "errors": [],
    }
    list(graph.compiled.stream(state, config, stream_mode="updates"))
    final = graph.compiled.get_state(config).values

    tool_runs = [node for node in recorder.nodes if node.node_kind == "tool"]
    assert len(tool_runs) == 1
    assert tool_runs[0].node_name == "find_matches"
    assert final["tool_calls"] == []
    assert len(gateway.calls) == 2
    assert final["tool_results"][0]["tool"] == "find_matches"
    assert final["tool_results"][0]["status"] == "ok"
