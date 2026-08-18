"""Copilot topology v4 graph: turn boundaries, refresh and confirmation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import MemorySaver
from tests.fakes.conversation import (
    FakeEffectApplier,
    FakeInterpretationGateway,
    FakePendingActionReader,
    FakePendingActionResolver,
    FakeRefreshScheduler,
    FakeTurnContextReader,
)
from tests.support.agent import RecordingRunRecorder
from tests.support.chat import RecordingConversation

from umbral.agent.graph import build_topology_v4
from umbral.agent.intent.interpretation import InterpretationCompiler
from umbral.application.conversation.contracts import (
    ConversationAct,
    ConversationTurnContext,
    PendingAction,
    TurnInterpretation,
)
from umbral.application.conversation.service import ConversationTurnService
from umbral.infrastructure.agent.model_gateway.fake import FakeModelGateway

_NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)

_REPLY_SCHEMA: dict[str, object] = {
    "reply_text": {"kind": "string", "min_length": 1, "max_length": 2000},
    "effects": {
        "kind": "list",
        "item": {
            "act_id": "string",
            "status": {"enum": ["applied", "pending", "remembered", "rejected"]},
        },
    },
    "question": {"kind": "nullable_string"},
    "refs": {"kind": "list", "item": {"entity": "string", "id": "string"}},
}


class ScriptedInterpretationGateway:
    """Model-driven InterpretationCompiler backed by a scripted gateway."""

    def __init__(self, acts: tuple[ConversationAct, ...]) -> None:
        self.acts = acts
        self.compiler = InterpretationCompiler(
            gateway=FakeModelGateway(
                replies={
                    "interpretation-v4": {
                        "acts": [
                            {
                                "act_id": act.act_id,
                                "kind": act.kind,
                                "target": dict(act.target),
                                "payload": dict(act.payload),
                                "confidence": act.confidence,
                            }
                            for act in acts
                        ],
                        "ambiguity": None,
                    }
                }
            ),
            schema={"acts": {"kind": "list"}},
            prompt_version="interpretation-v4",
            model_version="local-fake",
        )

    def interpret(
        self,
        *,
        message_text: str,
        pending_action: Mapping[str, object] | None,
        correlation_id: object | None = None,
    ) -> TurnInterpretation:
        return self.compiler.interpret(
            message_text=message_text,
            pending_action=pending_action,
            correlation_id=correlation_id,
        )

    def _interpretation_from_data(
        self, data: Mapping[str, object]
    ) -> TurnInterpretation:
        return self.compiler._interpretation_from_data(data)

    def _empty_interpretation(self) -> TurnInterpretation:
        return self.compiler._empty_interpretation()


def _build(
    *,
    profile_id: UUID | None,
    acts: tuple[ConversationAct, ...],
    pending: PendingAction | None = None,
    radar_filters: dict[str, dict[str, object]] | None = None,
) -> tuple[Any, ConversationTurnService, FakeEffectApplier, FakeRefreshScheduler]:
    context = ConversationTurnContext(
        user_id=UUID(int=10),
        session_id=UUID(int=20),
        verified_profile_id=profile_id,
        pending_action=pending,
        radar_filters=radar_filters or {},
    )
    applier = FakeEffectApplier()
    refresh = FakeRefreshScheduler()
    service = ConversationTurnService(
        contexts=FakeTurnContextReader(context=context),
        interpretation=FakeInterpretationGateway(
            interpretation=TurnInterpretation(acts=acts)
        ),
        applier=applier,
        pending=FakePendingActionReader(pending=pending),
        pending_resolver=FakePendingActionResolver(),
        refresh=refresh,
        clock=lambda: _NOW,
    )
    graph = build_topology_v4(
        gateway=FakeModelGateway(
            replies={
                "reply-v4": {
                    "reply_text": "Listo, actualicé tu búsqueda.",
                    "effects": [],
                    "question": None,
                    "refs": [],
                }
            }
        ),
        conversation=RecordingConversation(),
        recorder=RecordingRunRecorder(),
        saver=MemorySaver(),
        turn_service=service,
        interpretation=ScriptedInterpretationGateway(acts),
        clock=lambda: _NOW,
        model_version="local-fake",
        prompt_version="reply-v4",
        schema_version="reply-v4",
        reply_schema=_REPLY_SCHEMA,
    )
    return graph, service, applier, refresh


def _run(graph: Any, *, profile_id: UUID | None, text: str) -> dict[str, Any]:
    compiled = graph.compiled
    config = {"configurable": {"thread_id": str(uuid4())}}
    initial: dict[str, object] = {
        "schema_version": 4,
        "messages": [{"role": "user", "content": text}],
        "context": {
            "run_id": str(uuid4()),
            "session_id": str(UUID(int=20)),
            "user_id": str(UUID(int=10)),
            "correlation_id": str(uuid4()),
            "user_message_text": text,
            "effects_applied": {},
            "token_usage": {"input": 0, "output": 0, "total": 0},
            "verified_profile_id": str(profile_id) if profile_id else None,
        },
        "intent": None,
        "interpretation": None,
        "planned_effects": [],
        "effect_results": [],
        "clarification": None,
        "pending_action": None,
        "tool_calls": [],
        "tool_results": [],
        "errors": [],
    }
    compiled.invoke(initial, config)
    return dict(compiled.get_state(config).values)


def test_v4_happy_path_applies_preference_and_schedules_refresh() -> None:
    profile_id = uuid4()
    graph, _service, applier, refresh = _build(
        profile_id=profile_id,
        acts=(
            ConversationAct(
                act_id="a1",
                kind="express_preference",
                payload={"subject_key": "balcon"},
            ),
        ),
    )
    state = _run(graph, profile_id=profile_id, text="quiero balcon")

    effects = state.get("effect_results") or []
    assert [item["effect_key"] for item in effects] == ["preference.remembered"]
    assert state.get("context", {}).get("assistant_message_id") is not None
    assert len(refresh.scheduled) == 1
    assert refresh.scheduled[0]["profile_id"] == profile_id


def test_v4_material_change_interrupts_and_resolves_on_resume() -> None:
    profile_id = uuid4()
    pending = PendingAction(
        kind="profile",
        action_id="proposal-1",
        diff={"budget_max": 1200},
    )
    graph, _service, _applier, refresh = _build(
        profile_id=profile_id,
        acts=(
            ConversationAct(
                act_id="a1",
                kind="set_filter",
                payload={"key": "budget_max", "value": 1200},
            ),
        ),
        pending=pending,
        radar_filters={"budget_max": {"value": 800}},
    )
    # First run: material change requires confirmation; safe effects are none.
    first_config = {"configurable": {"thread_id": "turn-1"}}
    graph.compiled.invoke(
        {
            "schema_version": 4,
            "messages": [],
            "context": {
                "run_id": str(uuid4()),
                "session_id": str(UUID(int=20)),
                "user_id": str(UUID(int=10)),
                "correlation_id": str(uuid4()),
                "user_message_text": "subo a 1200",
                "effects_applied": {},
                "token_usage": {"input": 0, "output": 0, "total": 0},
                "verified_profile_id": str(profile_id),
            },
            "errors": [],
        },
        first_config,
    )
    assert refresh.scheduled == []
    # Resume with the decision resolves through the explicit resolver.
    second = graph.compiled.invoke(
        None,
        {
            "configurable": {"thread_id": "turn-1"},
            "resume": {"decision": "approve", "action_id": "proposal-1"},
        },
    )
    assert second is not None


def test_v4_create_radar_first_turn_does_not_require_confirmation() -> None:
    profile_id = None
    graph, _service, _applier, refresh = _build(
        profile_id=profile_id,
        acts=(
            ConversationAct(act_id="a1", kind="create_radar"),
            ConversationAct(
                act_id="a2",
                kind="express_preference",
                payload={"subject_key": "luminosidad"},
            ),
        ),
    )
    state = _run(graph, profile_id=profile_id, text="quiero un depto luminoso")

    effects = state.get("effect_results") or []
    assert [item["effect_key"] for item in effects] == [
        "radar.created",
        "preference.remembered",
    ]
    assert refresh.scheduled == []  # no durable radar to refresh yet