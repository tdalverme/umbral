# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Deterministic abuse suite v3 (UM-H4-017..UM-H4-021, T061).

Gate for the increment: intent policy violations, clarification bypass,
decision abuse and send replay must resolve deterministically with 0 effects
and 0 LLM involvement beyond scripted gateway outputs.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from langgraph.checkpoint.memory import MemorySaver
from tests.integration.chat.test_hitl_lifecycle import (
    NOW,
    SESSION_ID,
    USER_ID,
    _build,
    _NoopPreferenceGateway,
    _Repo,
)

from umbral.agent.intent.policy import validate_tool_calls
from umbral.application.chat.contracts import ChatSessionNotFound
from umbral.application.agent.tools.preferences import (
    load_preference_vocabulary,
)


def test_intent_policy_rejects_out_of_policy_tool() -> None:
    violations = validate_tool_calls(
        allowed_tools=["find_matches"],
        tool_calls=[{"tool": "apply_search_profile_update", "args": {}}],
    )
    assert len(violations) == 1
    assert violations[0].code == "agent.tool_not_allowed"


def test_malformed_tool_call_is_rejected() -> None:
    violations = validate_tool_calls(
        allowed_tools=["find_matches"], tool_calls=[{"args": {"page": 1}}]
    )
    assert len(violations) == 1


def test_clarification_bypass_never_proposes() -> None:
    """Low-confidence high-impact params always clarify: the propose tool call
    the reply would emit is never executed (0 proposals)."""

    from tests.support.agent import RecordingRunRecorder
    from tests.support.chat import RecordingConversation, RecordingEventWriter
    from tests.support.tools import (
        FakeCriteria,
        FakeFeedback,
        FakeRadar,
        FakeScoring,
    )

    from umbral.agent.graph import build_topology_v3
    from umbral.agent.intent.compiler import IntentCompiler
    from umbral.agent.tools.executor import ToolExecutor
    from umbral.agent.tools.registry import ToolRegistry
    from umbral.agent.tools.tools import ToolServices, build_tool_implementations
    from umbral.application.agent.contracts import ModelResult
    from umbral.application.agent.tools.ports import SessionScope
    from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
    from umbral.infrastructure.agent.intent.contract_loader import load_intent_contract
    from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract
    from umbral.infrastructure.radar.contract_loader import load_events_registry

    repo = _Repo()

    class LowConfidenceGateway:
        calls: list[str] = []

        def generate_structured(self, **kwargs):
            prompt = kwargs["prompt_version"]
            self.calls.append(prompt)
            if prompt == "agent-intent-v1":
                content = {
                    "intent": "refinamiento",
                    "parameters": [
                        {"key": "budget", "value": "900", "confidence": 0.4}
                    ],
                    "high_impact_missing": [],
                    "contradictions": [],
                }
            else:
                content = {
                    "reply_text": "Voy a proponer",
                    "refs": [],
                    "tool_calls": [
                        {
                            "tool": "propose_search_profile_update",
                            "args": {"change": {"budget_max": 900}},
                        }
                    ],
                }
            return ModelResult(
                content=content,
                model_version="local-fake",
                status="success",
                latency_ms=1,
                input_tokens=8,
                output_tokens=16,
                total_tokens=24,
            )

    proposals = SearchProfileUpdateProposals(
        repository=repo,
        radar=FakeRadar(),
        events=RecordingEventWriter(),
        events_registry=load_events_registry(),
        ttl_hours=24,
    )
    recorder = RecordingRunRecorder()
    executor = ToolExecutor(
        registry=ToolRegistry(load_tool_contract),
        implementations=build_tool_implementations(
            ToolServices(
                radar=FakeRadar(),
                scoring=FakeScoring(),
                feedback=FakeFeedback(),
                criteria=FakeCriteria(),
                proposals=proposals,
                vocabulary=load_preference_vocabulary(),
            )
        ),
        recorder=recorder,
        scope_reader=type(
            "R",
            (),
            {
                "read_scope": lambda self, user_id, session_id: SessionScope(
                    session_id=UUID(int=2),
                    search_profile_id=UUID(int=5),
                    status="active",
                )
            },
        )(),
        timeout_seconds=1.0,
    )
    gateway = LowConfidenceGateway()
    compiler = IntentCompiler(
        gateway=gateway,
        contract=load_intent_contract(),
        prompt_version="agent-intent-v1",
        model_version="local-fake",
    )
    graph = build_topology_v3(
        gateway=gateway,
        conversation=RecordingConversation(),
        recorder=recorder,
        saver=MemorySaver(),
        tool_executor=executor,
        intent_compiler=compiler,
        decision_gateway=proposals,
        preference_gateway=_NoopPreferenceGateway(),
        clock=lambda: NOW,
        model_version="local-fake",
        prompt_version="agent-reply-v2",
        schema_version="reply-v3",
        reply_schema={
            "reply_text": {"kind": "string"},
            "refs": {"kind": "list"},
            "tool_calls": {"kind": "list", "max_items": 5},
        },
        max_calls_per_turn=5,
        high_impact_keys=("budget", "zona", "hard_filters", "radio"),
        clarification_min_confidence=0.6,
        clarification_max_rounds=2,
        reply_chunk_words=8,
        reply_max_refs=10,
    )
    run_id = UUID(int=10)
    config = {"configurable": {"thread_id": str(run_id)}}
    state = {
        "schema_version": 3,
        "messages": [{"role": "user", "content": "quiero algo barato"}],
        "context": {
            "run_id": str(run_id),
            "session_id": str(UUID(int=2)),
            "user_id": str(USER_ID),
            "correlation_id": str(UUID(int=4)),
            "user_message_text": "quiero algo barato",
            "search_profile_id": str(UUID(int=5)),
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
    # The reply prompt was never used (0 propose call executed) and 0
    # proposals exist: the clarification short-circuited the tool loop.
    assert final["clarification"] is not None
    assert len(repo.proposals) == 0
    assert gateway.calls == ["agent-intent-v1"]


def test_resume_without_active_run_has_zero_effects() -> None:
    runtime, repo, _gateway = _build()
    try:
        runtime.run_turn(
            user_id=USER_ID,
            session_id=SESSION_ID,
            text="",
            correlation_id=UUID(int=41),
            resume=True,
            decision={"kind": "approve", "idempotency_key": "x"},
        )
    except Exception as exc:  # noqa: BLE001
        assert type(exc).__name__ == "AgentRunNotFound"
    else:
        raise AssertionError("expected AgentRunNotFound")
    assert len(repo.proposals) == 0


def test_decision_approve_after_reject_has_zero_effects() -> None:
    """Resuming a terminal run is rejected at the boundary: 0 effects."""
    runtime, repo, _gateway = _build()
    first = runtime.run_turn(
        user_id=USER_ID,
        session_id=SESSION_ID,
        text="subí el presupuesto a 900",
        correlation_id=UUID(int=40),
    )
    assert first.interrupt is not None
    proposal_id = UUID(str(first.interrupt["proposal_id"]))
    rejected = runtime.run_turn(
        user_id=USER_ID,
        session_id=SESSION_ID,
        text="",
        correlation_id=UUID(int=41),
        resume=True,
        decision={"kind": "reject", "reason": "no"},
    )
    assert rejected.status == "completed"
    assert repo.proposals[proposal_id].state == "rejected"
    # The run is terminal; a further resume cannot apply anything.
    try:
        runtime.run_turn(
            user_id=USER_ID,
            session_id=SESSION_ID,
            text="",
            correlation_id=UUID(int=42),
            resume=True,
            decision={"kind": "approve", "idempotency_key": "after-reject"},
        )
    except Exception as exc:  # noqa: BLE001
        assert type(exc).__name__ == "AgentRunNotFound"
    else:
        raise AssertionError("expected AgentRunNotFound")
    assert repo.proposals[proposal_id].state == "rejected"


def test_send_replay_does_not_duplicate_messages() -> None:
    """Idempotent send: replay with the same client_message_id is a no-op."""
    from tests.support.chat import (
        FixedProfileStatusReader,
        InMemoryChatMessageRepository,
        InMemoryChatSessionRepository,
        RecordingEventWriter,
    )

    from umbral.application.chat.service import ChatService
    from umbral.infrastructure.radar.contract_loader import load_events_registry

    messages = InMemoryChatMessageRepository()
    service = ChatService(
        sessions=InMemoryChatSessionRepository(),
        messages=messages,
        profile_status=FixedProfileStatusReader(),
        events_out=RecordingEventWriter(),
        events_registry=load_events_registry(),
        max_message_length=4000,
    )
    session = service.create_session(
        user_id=UUID(int=1), search_profile_id=UUID(int=5), correlation_id=UUID(int=9)
    )
    client_id = UUID(int=88)
    service.append_user_message(
        user_id=UUID(int=1),
        session_id=session.session_id,
        text="mensaje",
        correlation_id=UUID(int=10),
        client_message_id=client_id,
    )
    service.append_user_message(
        user_id=UUID(int=1),
        session_id=session.session_id,
        text="mensaje",
        correlation_id=UUID(int=11),
        client_message_id=client_id,
    )
    assert len(messages.list_by_session(session.session_id)) == 1


def test_cross_session_read_is_denied() -> None:
    from tests.support.chat import (
        FixedProfileStatusReader,
        InMemoryChatMessageRepository,
        InMemoryChatSessionRepository,
        RecordingEventWriter,
    )

    from umbral.application.chat.service import ChatService
    from umbral.infrastructure.radar.contract_loader import load_events_registry

    service = ChatService(
        sessions=InMemoryChatSessionRepository(),
        messages=InMemoryChatMessageRepository(),
        profile_status=FixedProfileStatusReader(),
        events_out=RecordingEventWriter(),
        events_registry=load_events_registry(),
        max_message_length=4000,
    )
    session = service.create_session(
        user_id=UUID(int=1), search_profile_id=UUID(int=5), correlation_id=UUID(int=9)
    )
    with pytest.raises(ChatSessionNotFound):
        service.get_session(user_id=UUID(int=999), session_id=session.session_id)
