"""Graph topology v1 conformance (FR-016)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from langgraph.checkpoint.memory import MemorySaver

from tests.support.agent import RecordingRunRecorder
from tests.support.chat import RecordingConversation
from umbral.agent.graph import (
    TOPOLOGY_VERSION,
    AgentGraph,
    build_input_state,
    build_topology_v1,
)
from umbral.infrastructure.agent.model_gateway.fake import FakeModelGateway

ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY_CONTRACT = json.loads(
    (ROOT / "contracts" / "agent" / "v1" / "graph-topology-v1.json").read_text(
        encoding="utf-8"
    )
)

_REPLY_SCHEMA = {"reply_text": {"kind": "string"}, "refs": {"kind": "list"}}


def _clock() -> datetime:
    return datetime.now(timezone.utc)


def _build() -> AgentGraph:
    return build_topology_v1(
        gateway=FakeModelGateway(),
        conversation=RecordingConversation(),
        recorder=RecordingRunRecorder(),
        saver=MemorySaver(),
        clock=_clock,
        model_version="local-fake",
        prompt_version="agent-chat-v1",
        schema_version="reply-v1",
        reply_schema=_REPLY_SCHEMA,
    )


def test_topology_contract_declares_v1_nodes_edges_no_tools() -> None:
    assert TOPOLOGY_CONTRACT["contract_version"] == "1"
    assert TOPOLOGY_CONTRACT["registry_version"] == "agent-graph-topology-v1"
    assert TOPOLOGY_CONTRACT["topology_version"] == TOPOLOGY_VERSION
    assert TOPOLOGY_CONTRACT["entry"] == "start"
    nodes = {node["name"] for node in TOPOLOGY_CONTRACT["nodes"]}
    assert nodes == {"start", "generate_reply", "persist_reply"}
    assert TOPOLOGY_CONTRACT["tools"] == []
    assert TOPOLOGY_CONTRACT["interrupts"] == []


def test_built_graph_matches_topology_v1() -> None:
    graph = _build()
    compiled_graph = graph.compiled.get_graph()
    node_names = {node for node in compiled_graph.nodes if not node.startswith("__")}
    assert node_names == {"start", "generate_reply", "persist_reply"}

    edges = {(edge.source, edge.target) for edge in compiled_graph.edges}
    assert ("start", "generate_reply") in edges
    assert ("generate_reply", "persist_reply") in edges
    assert ("persist_reply", "__end__") in edges


def test_built_graph_produces_structured_reply() -> None:
    graph = _build()
    run_id = UUID(int=10)
    state = build_input_state(
        run_id=run_id,
        session_id=UUID(int=20),
        user_id=UUID(int=30),
        correlation_id=UUID(int=40),
        user_message_text="hola",
    )
    config = {"configurable": {"thread_id": str(run_id)}}
    list(graph.compiled.stream(state, config, stream_mode="updates"))
    final = graph.compiled.get_state(config).values
    reply = dict(final["context"]).get("generated_reply")
    assert isinstance(reply, dict)
    assert str(reply.get("text", "")).startswith("Respuesta")
    assert reply.get("refs") == []
