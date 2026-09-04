# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Chat streaming router over TestClient: SSE events and typed errors (T033)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from tests.integration.chat.test_hitl_lifecycle import (
    _NoopPreferenceGateway,
    _Repo,
    _ScopeReader,
    _ScriptedGateway,
)
from tests.support.agent import InMemoryGraphRunRepository, RecordingRunRecorder
from tests.support.chat import (
    FixedProfileStatusReader,
    InMemoryChatMessageRepository,
    InMemoryChatSessionRepository,
    RecordingEventWriter,
)
from tests.support.tools import FakeCriteria, FakeFeedback, FakeRadar, FakeScoring

from umbral.agent.graph import build_topology_v3
from umbral.agent.intent.compiler import IntentCompiler
from umbral.agent.runtime import ChatRuntime
from umbral.agent.state import CHAT_STATE_SCHEMA_VERSION
from umbral.agent.tools.executor import ToolExecutor
from umbral.agent.tools.registry import ToolRegistry
from umbral.agent.tools.tools import ToolServices, build_tool_implementations
from umbral.api.main import app
from umbral.api.routers import chat as chat_router
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.chat.service import ChatService
from umbral.application.identity.contracts import CurrentPrincipal
from umbral.infrastructure.agent.intent.contract_loader import load_intent_contract
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract
from umbral.application.agent.tools.preferences import (
    load_preference_vocabulary,
)
from umbral.infrastructure.radar.contract_loader import load_events_registry

USER_ID = UUID(int=1)
PROFILE_ID = UUID(int=5)
NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)

_REPLY_SCHEMA = {
    "reply_text": {"kind": "string"},
    "refs": {"kind": "list"},
    "tool_calls": {"kind": "list", "max_items": 5},
}


class _FakeAccess:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id

    def authorize(
        self, token, *, action, resource_owner_id=None, now=None, correlation_id=None
    ):
        return CurrentPrincipal(
            user_id=self.user_id,
            roles=("user",),
            last_activity_at=datetime.now(timezone.utc),
        )


def _build_stack() -> tuple[TestClient, _Repo, ChatService]:
    repo = _Repo()
    radar = FakeRadar()
    proposals = SearchProfileUpdateProposals(
        repository=repo,
        radar=radar,
        events=RecordingEventWriter(),
        events_registry=load_events_registry(),
        ttl_hours=24,
        clock=lambda: NOW,
    )
    chat = ChatService(
        sessions=InMemoryChatSessionRepository(),
        messages=InMemoryChatMessageRepository(),
        profile_status=FixedProfileStatusReader({PROFILE_ID: "active"}),
        events_out=RecordingEventWriter(),
        events_registry=load_events_registry(),
        max_message_length=4000,
        clock=lambda: NOW,
    )
    runs = InMemoryGraphRunRepository()
    recorder = RecordingRunRecorder()
    registry = ToolRegistry(load_tool_contract)
    executor = ToolExecutor(
        registry=registry,
        implementations=build_tool_implementations(
            ToolServices(
                radar=radar,
                scoring=FakeScoring(),
                feedback=FakeFeedback(),
                criteria=FakeCriteria(),
                proposals=proposals,
                vocabulary=load_preference_vocabulary(),
            )
        ),
        recorder=recorder,
        scope_reader=_ScopeReader(),
        timeout_seconds=1.0,
    )
    gateway = _ScriptedGateway(
        [
            {
                "reply_text": "Voy a proponer el cambio.",
                "refs": [],
                "tool_calls": [
                    {
                        "tool": "propose_search_profile_update",
                        "args": {"change": {"budget_max": 900}},
                    }
                ],
            },
            {"reply_text": "ApliquÃ© el cambio.", "refs": [], "tool_calls": []},
        ]
    )
    compiler = IntentCompiler(
        gateway=gateway,
        contract=load_intent_contract(),
        prompt_version="agent-intent-v1",
        model_version="local-fake",
    )
    graph = build_topology_v3(
        gateway=gateway,
        conversation=chat,
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
        reply_schema=_REPLY_SCHEMA,
        max_calls_per_turn=5,
        high_impact_keys=("budget", "zona", "hard_filters", "radio"),
        clarification_min_confidence=0.6,
        clarification_max_rounds=2,
        reply_chunk_words=8,
        reply_max_refs=10,
    )
    runtime = ChatRuntime(
        graph=graph,
        conversation=chat,
        runs=runs,
        recorder=recorder,
        clock=lambda: NOW,
        state_schema_version=CHAT_STATE_SCHEMA_VERSION,
        topology_version=3,
    )
    deps = SimpleNamespace(
        settings=SimpleNamespace(session_cookie_name="test_session"),
        access_control=_FakeAccess(USER_ID),
        chat=chat,
        agent_runtime=runtime,
        proposals=proposals,
        graph_runs=runs,
    )
    chat_router.configure_chat_routes(deps)
    client = TestClient(app)
    client.cookies.set("test_session", "token-1")
    return client, repo, chat


def test_send_message_streams_events_and_interrupt() -> None:
    client, _repo, chat = _build_stack()
    created = client.post(
        "/api/v1/chat/sessions", json={"search_profile_id": str(PROFILE_ID)}
    )
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    stream = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"text": "subÃ­ el presupuesto a 900"},
    )
    assert stream.status_code == 200
    body = stream.text
    assert "event: chat.run_started" in body
    assert "event: chat.reply_fragment" in body
    assert "event: chat.interrupt_waiting" in body
    assert "proposal_decision" in body


def test_decision_approve_completes_and_applies() -> None:
    client, repo, chat = _build_stack()
    created = client.post(
        "/api/v1/chat/sessions", json={"search_profile_id": str(PROFILE_ID)}
    )
    session_id = created.json()["session_id"]
    stream = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"text": "subÃ­ el presupuesto a 900"},
    )
    proposal_id = _extract_proposal_id(stream.text)
    run_id = _extract_run_id(stream.text)
    assert proposal_id is not None
    assert run_id is not None

    decision = client.post(
        f"/api/v1/chat/sessions/{session_id}/runs/{run_id}/decision",
        json={"kind": "approve", "idempotency_key": "key-1"},
    )
    assert decision.status_code == 200
    assert "event: chat.run_completed" in decision.text
    assert repo.proposals[UUID(proposal_id)].state == "approved"


def test_send_while_decision_pending_returns_typed_error() -> None:
    client, _repo, chat = _build_stack()
    created = client.post(
        "/api/v1/chat/sessions", json={"search_profile_id": str(PROFILE_ID)}
    )
    session_id = created.json()["session_id"]
    stream = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"text": "subÃ­ el presupuesto a 900"},
    )
    assert stream.status_code == 200
    second = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"text": "hola de nuevo"},
    )
    assert second.status_code == 409
    assert second.json()["code"] == "chat.decision_pending"


def test_send_confirmo_resumes_pending_decision() -> None:
    client, repo, _chat = _build_stack()
    created = client.post(
        "/api/v1/chat/sessions", json={"search_profile_id": str(PROFILE_ID)}
    )
    session_id = created.json()["session_id"]
    stream = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"text": "subÃƒÂ­ el presupuesto a 900"},
    )
    proposal_id = _extract_proposal_id(stream.text)
    assert proposal_id is not None

    confirmed = client.post(
        f"/api/v1/chat/sessions/{session_id}/messages",
        json={"text": "Confirmo"},
    )

    assert confirmed.status_code == 200
    assert "event: chat.run_completed" in confirmed.text
    assert repo.proposals[UUID(proposal_id)].state == "approved"


def _extract_proposal_id(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("data: "):
            import json

            payload = json.loads(line[len("data: ") :])
            interrupt = payload.get("interrupt")
            if (
                isinstance(interrupt, dict)
                and interrupt.get("type") == "proposal_decision"
            ):
                return str(interrupt.get("proposal_id"))
    return None


def _extract_run_id(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("data: "):
            import json

            payload = json.loads(line[len("data: ") :])
            if payload.get("run_id"):
                return str(payload.get("run_id"))
    return None
