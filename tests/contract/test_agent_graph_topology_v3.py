# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Graph topology v3 conformance: intent, clarification and HITL nodes (T017)."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, Interrupt

from tests.support.agent import RecordingRunRecorder
from tests.support.chat import RecordingConversation
from tests.support.tools import (
    FakeServices,
)
from umbral.agent.graph import (
    CHAT_TOPOLOGY_VERSION,
    AgentGraphV3,
    build_topology_v3,
)
from umbral.agent.tools.executor import ToolExecutor
from umbral.agent.tools.registry import ToolRegistry
from umbral.agent.tools.tools import ToolServices, build_tool_implementations
from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.tools.ports import SessionScope
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract
from umbral.infrastructure.agent.tools.preferences_loader import (
    load_preference_vocabulary,
)

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


class _NoopPreferences:
    def get_proposal(self, **kwargs: object) -> object:
        raise AssertionError("preference gateway must not be called here")

    def confirm_proposal(self, **kwargs: object) -> object:
        raise AssertionError("preference gateway must not be called here")

    def confirm_preference_removal(self, **kwargs: object) -> object:
        raise AssertionError("preference gateway must not be called here")

    def reject_proposal(self, **kwargs: object) -> object:
        raise AssertionError("preference gateway must not be called here")


class _FakeCompiler:
    def __init__(self, compilation: Mapping[str, Any]) -> None:
        self._compilation = compilation

    def compile(self, **kwargs: object) -> object:
        return _CompilationResult(self._compilation)


class _CompilationResult:
    def __init__(self, data: Mapping[str, Any]) -> None:
        self.intent = str(data.get("intent", ""))
        self.allowed_tools = tuple(data.get("allowed_tools", []))
        self.parameters = tuple(data.get("parameters", []))
        self.high_impact_missing = tuple(data.get("high_impact_missing", []))
        self.contradictions = tuple(data.get("contradictions", []))


def _build(
    compilation: Mapping[str, Any],
    *,
    gateway: "_Gateway | None" = None,
    implementations: (
        Mapping[str, Callable[..., Mapping[str, object]]] | None
    ) = None,
    preference_gateway: object | None = None,
) -> AgentGraphV3:
    recorder = RecordingRunRecorder()
    registry = ToolRegistry(load_tool_contract)
    scope = SessionScope(
        session_id=UUID(int=2), search_profile_id=UUID(int=5), status="active"
    )
    executor = ToolExecutor(
        registry=registry,
        implementations=implementations or {},
        recorder=recorder,
        scope_reader=_ScopeReader(scope),
        timeout_seconds=1.0,
    )
    return build_topology_v3(
        gateway=gateway
        or _Gateway([{"reply_text": "ok", "refs": [], "tool_calls": []}]),
        conversation=RecordingConversation(),
        recorder=recorder,
        saver=MemorySaver(),
        tool_executor=executor,
        intent_compiler=_FakeCompiler(compilation),  # type: ignore[arg-type]
        decision_gateway=_NoopDecisions(),  # type: ignore[arg-type]
        preference_gateway=preference_gateway or _NoopPreferences(),  # type: ignore[arg-type]
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


def test_built_graph_v3_runs_consulta_turn_to_completion() -> None:
    graph = _build({"intent": "consulta", "allowed_tools": []})
    run_id = UUID(int=10)
    config = {"configurable": {"thread_id": str(run_id)}}
    state = {
        "schema_version": 3,
        "messages": [{"role": "user", "content": "qu� criterios tengo?"}],
        "context": {
            "run_id": str(run_id),
            "session_id": str(UUID(int=2)),
            "user_id": str(UUID(int=3)),
            "correlation_id": str(UUID(int=4)),
            "user_message_text": "qu� criterios tengo?",
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


def test_built_graph_v3_injects_idempotency_key_for_feedback() -> None:
    received: dict[str, object] = {}

    def record_feedback(_ctx, args):
        received.update(dict(args))
        return {
            "event_id": str(UUID(int=99)),
            "noop": False,
            "learning_proposal_id": None,
        }

    listing_id = str(UUID(int=70))
    gateway = _Gateway(
        [
            {
                "reply_text": "registro",
                "refs": [],
                "tool_calls": [
                    {
                        "tool": "record_feedback",
                        "args": {
                            "listing_id": listing_id,
                            "decision": "dislike",
                            "reason_keys": [],
                        },
                    }
                ],
            },
            {"reply_text": "listo", "refs": [], "tool_calls": []},
        ]
    )
    graph = _build(
        {"intent": "feedback", "allowed_tools": ["record_feedback"]},
        gateway=gateway,
        implementations={"record_feedback": record_feedback},
    )
    run_id = UUID(int=11)
    config = {"configurable": {"thread_id": str(run_id)}}
    state = {
        "schema_version": 3,
        "messages": [{"role": "user", "content": "no me gusta"}],
        "context": {
            "run_id": str(run_id),
            "session_id": str(UUID(int=2)),
            "user_id": str(UUID(int=3)),
            "correlation_id": str(UUID(int=4)),
            "user_message_text": "no me gusta",
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
    assert received["listing_id"] == listing_id
    assert received["decision"] == "dislike"
    assert received["idempotency_key"] == (
        f"chat:{UUID(int=2)}:{listing_id}:dislike"
    )
    assert any(
        item.get("tool") == "record_feedback" and item.get("status") == "ok"
        for item in final["tool_results"]
    )


class _RecordingPreferenceGateway:
    def __init__(self) -> None:
        self.confirmed: list[UUID] = []
        self.removed: list[UUID] = []
        self.rejected: list[UUID] = []

    def get_proposal(
        self, *, owner_id: UUID, profile_id: UUID, proposal_id: UUID
    ) -> object:
        from datetime import datetime, timezone

        from umbral.application.feedback.contracts import (
            LearningProposal,
            ProposalChange,
        )

        return LearningProposal(
            proposal_id=proposal_id,
            profile_id=profile_id,
            concept_id=UUID(int=96),
            concept_key="luminosidad",
            policy_version_id=UUID(int=97),
            policy_version="1",
            change=ProposalChange(
                kind="preference_fact",
                concept_key="luminosidad",
                polarity="negative",
                suggested_weight=0.3,
                suggested_confidence=0.6,
                value=None,
            ),
            prior_fact=None,
            evidence_refs=(),
            state="pending",
            expires_at=datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc),
            superseded_by=None,
            applied_profile_version_id=None,
            applied_run_id=None,
            created_at=datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
            correlation_id=UUID(int=4),
        )

    def confirm_proposal(self, **kwargs: object) -> object:
        self.confirmed.append(UUID(str(kwargs["proposal_id"])))
        return None

    def confirm_preference_removal(self, **kwargs: object) -> object:
        self.removed.append(UUID(str(kwargs["proposal_id"])))
        return None

    def reject_proposal(self, **kwargs: object) -> object:
        self.rejected.append(UUID(str(kwargs["proposal_id"])))
        return None


def _run_state(run_id: UUID, text: str) -> dict[str, object]:
    return {
        "schema_version": 3,
        "messages": [{"role": "user", "content": text}],
        "context": {
            "run_id": str(run_id),
            "session_id": str(UUID(int=2)),
            "user_id": str(UUID(int=3)),
            "search_profile_id": str(UUID(int=5)),
            "correlation_id": str(UUID(int=4)),
            "user_message_text": text,
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


def _interrupt_value(chunk: object) -> Any | None:
    if not isinstance(chunk, dict):
        return None
    for value in chunk.values():
        if isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, Interrupt):
                    return item.value
    return None


def test_built_graph_v3_preference_hitl_confirms_and_recomputes() -> None:
    services = FakeServices()
    implementations = build_tool_implementations(
        ToolServices(
            radar=services.radar,
            scoring=services.scoring,
            feedback=services.feedback,
            criteria=services.criteria,
            proposals=services.proposals,  # type: ignore[arg-type]
            vocabulary=load_preference_vocabulary(),
        )
    )
    preference_gateway = _RecordingPreferenceGateway()
    gateway = _Gateway(
        [
            {
                "reply_text": "propongo",
                "refs": [],
                "tool_calls": [
                    {
                        "tool": "propose_search_preference_update",
                        "args": {"preference": "luminoso"},
                    }
                ],
            },
            {"reply_text": "listo", "refs": [], "tool_calls": []},
        ]
    )
    graph = _build(
        {
            "intent": "refinamiento",
            "allowed_tools": ["propose_search_preference_update"],
        },
        gateway=gateway,
        implementations=implementations,
        preference_gateway=preference_gateway,
    )
    run_id = UUID(int=12)
    config = {"configurable": {"thread_id": str(run_id)}}
    interrupted: list[object] = []
    for chunk in graph.compiled.stream(
        _run_state(run_id, "quiero un depto luminoso"),
        config,
        stream_mode="updates",
    ):
        value = _interrupt_value(chunk)
        if value is not None:
            interrupted.append(value)
    assert len(interrupted) == 1
    payload = interrupted[0]
    assert isinstance(payload, dict)
    assert payload["type"] == "proposal_decision"
    assert payload["kind"] == "preference"
    assert payload["diff"]["concept_key"] == "luminosidad"
    assert payload["diff"]["polarity"] == "positive"
    assert payload["proposal_id"]

    for chunk in graph.compiled.stream(
        Command(resume={"kind": "approve"}), config, stream_mode="updates"
    ):
        _interrupt_value(chunk)
    final = graph.compiled.get_state(config).values
    assert final["errors"] == []
    assert len(preference_gateway.confirmed) == 1
    assert UUID(str(payload["proposal_id"])) == preference_gateway.confirmed[0]
    assert any(
        item.get("tool") == "propose_search_preference_update"
        and item.get("status") == "ok"
        for item in final["tool_results"]
    )
    assert any(
        item.get("tool") == "confirm_search_preference"
        and item.get("status") == "ok"
        and item.get("result", {}).get("applied") is True
        for item in final["context"]["tool_results_context"]
    )


def test_built_graph_v3_preference_removal_hitl_confirms() -> None:
    services = FakeServices()
    implementations = build_tool_implementations(
        ToolServices(
            radar=services.radar,
            scoring=services.scoring,
            feedback=services.feedback,
            criteria=services.criteria,
            proposals=services.proposals,  # type: ignore[arg-type]
            vocabulary=load_preference_vocabulary(),
        )
    )
    preference_gateway = _RecordingPreferenceGateway()
    gateway = _Gateway(
        [
            {
                "reply_text": "quito",
                "refs": [],
                "tool_calls": [
                    {
                        "tool": "propose_search_preference_removal",
                        "args": {"preference": "luminosidad"},
                    }
                ],
            },
            {"reply_text": "listo", "refs": [], "tool_calls": []},
        ]
    )
    graph = _build(
        {
            "intent": "refinamiento",
            "allowed_tools": ["propose_search_preference_removal"],
        },
        gateway=gateway,
        implementations=implementations,
        preference_gateway=preference_gateway,
    )
    run_id = UUID(int=13)
    config = {"configurable": {"thread_id": str(run_id)}}
    interrupted: list[object] = []
    for chunk in graph.compiled.stream(
        _run_state(run_id, "saca la preferencia de luminosidad"),
        config,
        stream_mode="updates",
    ):
        value = _interrupt_value(chunk)
        if value is not None:
            interrupted.append(value)
    assert len(interrupted) == 1
    payload = interrupted[0]
    assert isinstance(payload, dict)
    assert payload["kind"] == "preference"
    assert payload["diff"]["operation"] == "remove"
    assert payload["diff"]["concept_key"] == "luminosidad"

    for chunk in graph.compiled.stream(
        Command(resume={"kind": "approve"}), config, stream_mode="updates"
    ):
        _interrupt_value(chunk)
    final = graph.compiled.get_state(config).values
    assert final["errors"] == []
    assert len(preference_gateway.removed) == 1
    assert UUID(str(payload["proposal_id"])) == preference_gateway.removed[0]
    assert preference_gateway.confirmed == []


def test_built_graph_v3_learning_confirmation_hitl_confirms() -> None:
    services = FakeServices()
    implementations = build_tool_implementations(
        ToolServices(
            radar=services.radar,
            scoring=services.scoring,
            feedback=services.feedback,
            criteria=services.criteria,
            proposals=services.proposals,  # type: ignore[arg-type]
            vocabulary=load_preference_vocabulary(),
        )
    )
    preference_gateway = _RecordingPreferenceGateway()
    gateway = _Gateway(
        [
            {
                "reply_text": "registro",
                "refs": [],
                "tool_calls": [
                    {
                        "tool": "record_feedback",
                        "args": {
                            "listing_id": str(UUID(int=70)),
                            "decision": "like",
                            "reason_keys": ["balcony_wanted"],
                            "idempotency_key": "k-learn-1",
                        },
                    }
                ],
            },
            {"reply_text": "listo", "refs": [], "tool_calls": []},
        ]
    )
    graph = _build(
        {
            "intent": "refinamiento",
            "allowed_tools": [
                "record_feedback",
                "propose_learning_confirmation",
            ],
        },
        gateway=gateway,
        implementations=implementations,
        preference_gateway=preference_gateway,
    )
    run_id = UUID(int=14)
    config = {"configurable": {"thread_id": str(run_id)}}
    interrupted: list[object] = []
    for chunk in graph.compiled.stream(
        _run_state(run_id, "me gusta este depto, quiero balcon"),
        config,
        stream_mode="updates",
    ):
        value = _interrupt_value(chunk)
        if value is not None:
            interrupted.append(value)
    assert len(interrupted) == 1
    payload = interrupted[0]
    assert isinstance(payload, dict)
    assert payload["kind"] == "preference"
    assert payload["diff"]["concept_key"] == "luminosidad"
    assert payload["proposal_id"] == str(UUID(int=90))

    for chunk in graph.compiled.stream(
        Command(resume={"kind": "approve"}), config, stream_mode="updates"
    ):
        _interrupt_value(chunk)
    final = graph.compiled.get_state(config).values
    assert final["errors"] == []
    assert len(preference_gateway.confirmed) == 1
    assert UUID(int=90) == preference_gateway.confirmed[0]
    assert any(
        item.get("tool") == "record_feedback" and item.get("status") == "ok"
        for item in final["tool_results"]
    )
    assert any(
        item.get("tool") == "confirm_search_preference"
        and item.get("status") == "ok"
        for item in final["context"]["tool_results_context"]
    )
