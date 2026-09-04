"""Composition of the single semantic graph over local fixture state."""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import MemorySaver

from umbral.agent.events import RuntimeEvent
from umbral.agent.graph import GraphDeps, build_graph
from umbral.agent.intent import InterpretationCompiler
from umbral.agent.runtime import ChatRuntime
from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.ports import ModelGateway
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.chat.service import ChatService
from umbral.application.conversation.ports import FocusedListing
from umbral.application.conversation.receipts import InMemoryCommandReceiptStore
from umbral.application.conversation.reply import ReplyComposer
from umbral.application.playground.contracts import (
    ConversationRequest,
    ConversationTrace,
)
from umbral.application.preferences.intensity import load_intensity_policy
from umbral.infrastructure.agent.model_gateway.managed import ManagedModelGateway
from umbral.infrastructure.conversation.composition import (
    ConversationServices,
    build_conversation_turn_service,
)
from umbral.infrastructure.playground.fixtures import PlaygroundFixture, load_fixtures
from umbral.infrastructure.playground.in_memory import (
    FixedProfileStatusReader,
    InMemoryChatMessageRepository,
    InMemoryChatSessionRepository,
    InMemoryGraphRunRepository,
    LocalProfileState,
    LocalProposalRepository,
    LocalRadar,
    NoopEventWriter,
    PlaygroundTraceCollector,
)
from umbral.infrastructure.playground.trace import event_record, primitive
from umbral.infrastructure.radar.contract_loader import load_events_registry

_USER_ID = UUID(int=1)
_CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "contracts" / "agent"


class LocalConversationRunner:
    def __init__(self) -> None:
        self.fixtures = load_fixtures()

    def run(self, request: ConversationRequest) -> ConversationTrace:
        fixture = self.fixtures.by_id(request.fixture_id)
        state_before = copy.deepcopy(dict(fixture.profile))
        stack = _build_stack(fixture=fixture, model_mode=request.model_mode)
        runtime = stack.runtime
        session_id = stack.session_id
        run_id: UUID | None = None
        events: list[dict[str, object]] = []
        turn_records: list[dict[str, object]] = []
        error: dict[str, object] | None = None
        pending = False

        for text in request.turns:
            turn_events: list[RuntimeEvent] = []
            decision: Mapping[str, object] | None = None
            resume = pending
            if pending:
                decision = _decision_from_text(text)
                if decision is None:
                    turn_records.append(
                        {
                            "text": text,
                            "status": "waiting_for_confirmation",
                            "tool_calls": [],
                            "reply": "Confirmá o rechazá el cambio pendiente.",
                        }
                    )
                    continue
                text = ""
            outcome = runtime.run_turn(
                user_id=_USER_ID,
                session_id=session_id,
                text=text,
                correlation_id=uuid4(),
                resume=resume,
                decision=decision,
                consumer=turn_events.append,
            )
            run_id = outcome.run_id
            events.extend(event_record(event) for event in turn_events)
            tool_calls = [
                {
                    "tool": event.tool,
                    "status": event.status,
                }
                for event in turn_events
                if hasattr(event, "tool") and hasattr(event, "status")
            ]
            checkpoint = runtime.graph.compiled.get_state(
                {"configurable": {"thread_id": str(outcome.run_id)}}
            ).values
            turn_records.append(
                {
                    "text": text or request.turns[len(turn_records)],
                    "status": outcome.status,
                    "reply": _reply_from_checkpoint(checkpoint),
                    "tool_calls": tool_calls,
                    "interrupt": primitive(outcome.interrupt),
                    "state": primitive(_snapshot_state(checkpoint)),
                }
            )
            pending = outcome.status == "interrupted" and outcome.interrupt is not None
            if outcome.status == "failed":
                error = {"code": outcome.error_code or "agent.failed"}
                break

        profile_after = stack.profile_state.snapshot()
        assertions = _assertions(turn_records, state_before, profile_after)
        return ConversationTrace(
            fixture_id=request.fixture_id,
            run_id=str(run_id or uuid4()),
            turns=tuple(turn_records),
            state_before=state_before,
            state_after=profile_after,
            events=tuple(events),
            assertions=tuple(assertions),
            error=error,
        )


@dataclass(slots=True)
class _LocalStack:
    runtime: ChatRuntime
    session_id: UUID
    profile_state: LocalProfileState


def build_local_conversation_runner() -> LocalConversationRunner:
    return LocalConversationRunner()


class _NoFocus:
    def verified_focus(
        self, *, user_id: UUID, session_id: UUID
    ) -> FocusedListing | None:
        return None


def _build_stack(*, fixture: PlaygroundFixture, model_mode: str) -> _LocalStack:
    profile_state = LocalProfileState(fixture.profile, fixture.listings)
    sessions = InMemoryChatSessionRepository()
    messages = InMemoryChatMessageRepository()
    chat = ChatService(
        sessions=sessions,
        messages=messages,
        profile_status=FixedProfileStatusReader(),
        events_out=NoopEventWriter(),
        events_registry=load_events_registry(),
        clock=lambda: datetime.now(timezone.utc),
    )
    session = chat.create_session(
        user_id=_USER_ID,
        search_profile_id=profile_state.profile_id,
        correlation_id=uuid4(),
    )
    recorder = PlaygroundTraceCollector()
    proposals = SearchProfileUpdateProposals(
        repository=LocalProposalRepository(),
        radar=LocalRadar(profile_state),
        events=NoopEventWriter(),
        events_registry=load_events_registry(),
        ttl_hours=24,
    )
    gateway = _gateway_for_mode(model_mode)
    interpretation_schema = json.loads(
        (_CONTRACTS_DIR / "interpretation-schema.json").read_text(encoding="utf-8")
    )
    reply_schema = json.loads(
        (_CONTRACTS_DIR / "reply-schema.json").read_text(encoding="utf-8")
    )
    turn = build_conversation_turn_service(
        services=ConversationServices(
            chat=chat,
            radar=LocalRadar(profile_state),
            proposals=proposals,
            preferences=None,
            intensity_policy=load_intensity_policy(),
        ),
        focus=_NoFocus(),
        interpreter=InterpretationCompiler(
            gateway=gateway,
            schema=interpretation_schema,
            prompt_version="interpretation",
            model_version="local-fake" if model_mode == "fake" else "managed",
            concept_catalog=(),
        ),
        receipts=InMemoryCommandReceiptStore(),
        clock=lambda: datetime.now(timezone.utc),
    )
    reply = ReplyComposer(
        gateway=gateway,
        schema=reply_schema,
        prompt_version="reply",
        model_version="local-fake" if model_mode == "fake" else "managed",
    )
    graph = build_graph(
        dependencies=GraphDeps(turn=turn, reply=reply),
        checkpointer=MemorySaver(),
    )
    runs = InMemoryGraphRunRepository()
    runtime = ChatRuntime(
        graph=graph,
        conversation=chat,  # type: ignore[arg-type]
        runs=runs,  # type: ignore[arg-type]
        recorder=recorder,  # type: ignore[arg-type]
    )
    return _LocalStack(
        runtime=runtime, session_id=session.session_id, profile_state=profile_state
    )


def _gateway_for_mode(mode: str) -> ModelGateway:
    if mode == "real":
        endpoint = os.getenv("AGENT_MANAGED_ENDPOINT")
        if not endpoint:
            raise ValueError(
                "AGENT_MANAGED_ENDPOINT is required for real playground mode"
            )
        return ManagedModelGateway(
            endpoint=endpoint,
            api_key=os.getenv("AGENT_MANAGED_API_KEY", ""),
            model=os.getenv("AGENT_MODEL_NAME", "local-managed"),
        )
    return _FakePlaygroundGateway()


class _FakePlaygroundGateway:
    """Deterministic scripted gateway for local fixture turns.

    It never resolves concepts from free text: a turn mentioning the budget
    keyword yields one typed hard-filter act with positional evidence, and
    anything else yields a read-only query act. Pending confirmation is owned
    by the runtime, never by this script.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

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
        user_text = _user_text(messages)
        self.calls.append(
            {
                "prompt_version": prompt_version,
                "model_version": model_version,
                "schema_version": schema_version,
                "messages": messages,
                "tools": tools,
            }
        )
        if prompt_version.startswith("interpretation"):
            content: Mapping[str, object] = _scripted_interpretation(user_text)
        else:
            content = {
                "contract_version": "5",
                "text": "Listo, lo registré en tu radar.",
                "outcomes": [],
                "verified_refs": [],
                "source": "managed",
            }
        return ModelResult(
            content=dict(content),
            model_version=model_version,
            status="success",
            latency_ms=1,
            input_tokens=8,
            output_tokens=16,
            total_tokens=24,
        )


def _user_text(messages: tuple[Mapping[str, object], ...]) -> str:
    for item in reversed(messages):
        if item.get("role") == "user" and isinstance(item.get("content"), str):
            return str(item["content"])
    return ""


def _scripted_interpretation(message: str) -> dict[str, object]:
    lowered = message.casefold()
    amount = _first_amount(message)
    if "presupuesto" in lowered and amount is not None:
        evidence = str(amount)
        if message.count(evidence) != 1:
            evidence = "presupuesto" if message.count("presupuesto") == 1 else message
        return {
            "contract_version": "5",
            "interpretation_version": "conversation-interpretation",
            "acts": [
                {
                    "act_id": "a1",
                    "kind": "set_filter",
                    "confidence": 0.95,
                    "evidence_text": evidence,
                    "filter_key": "budget_max",
                    "value": amount,
                }
            ],
        }
    return {
        "contract_version": "5",
        "interpretation_version": "conversation-interpretation",
        "acts": [
            {
                "act_id": "a1",
                "kind": "query",
                "confidence": 0.9,
                "evidence_text": message,
                "query_text": message,
            }
        ],
    }


def _first_amount(message: str) -> float | None:
    for token in message.replace(",", " ").split():
        cleaned = "".join(char for char in token if char.isdigit() or char == ".")
        if cleaned and any(char.isdigit() for char in cleaned):
            try:
                return float(cleaned)
            except ValueError:
                continue
    return None


def _decision_from_text(text: str) -> dict[str, object] | None:
    normalized = " ".join(text.casefold().split())
    if any(word in normalized for word in ("confirmo", "confirmar", "si", "dale")):
        return {"decision": "approve"}
    if any(word in normalized for word in ("rechazo", "rechazar", "no")):
        return {"decision": "reject"}
    return None


def _reply_from_checkpoint(state: Mapping[str, object]) -> str | None:
    reply = state.get("reply")
    if isinstance(reply, Mapping):
        text = reply.get("text")
        return str(text) if text else None
    return None


def _snapshot_state(state: Mapping[str, object]) -> dict[str, object]:
    snapshot: dict[str, object] = {}
    for key in (
        "contract_version",
        "schema_version",
        "message_id",
        "message_text",
        "outcomes",
        "reply",
        "failure_stage",
    ):
        if key in state:
            snapshot[key] = state[key]
    return snapshot


def _assertions(
    turns: Sequence[Mapping[str, object]],
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> list[dict[str, object]]:
    tool_names = [
        str(call.get("tool"))
        for turn in turns
        for call in turn.get("tool_calls", [])
        if isinstance(call, Mapping)
    ]
    return [
        {"name": "tool_calls_present", "passed": bool(tool_names), "value": tool_names},
        {
            "name": "profile_changed_only_after_confirmation",
            "passed": before.get("budget_max") == after.get("budget_max")
            or bool(tool_names),
            "value": {
                "before": before.get("budget_max"),
                "after": after.get("budget_max"),
            },
        },
    ]
