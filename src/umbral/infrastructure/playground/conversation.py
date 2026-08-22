"""Composition of the existing v3 agent graph over local fixture state."""

from __future__ import annotations

import copy
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import MemorySaver

from umbral.agent.events import RuntimeEvent
from umbral.agent.graph import CHAT_TOPOLOGY_VERSION, build_topology_v3
from umbral.agent.intent.compiler import IntentCompiler
from umbral.agent.runtime import ChatRuntime
from umbral.agent.state import CHAT_STATE_SCHEMA_VERSION, as_serializable
from umbral.agent.tools.contracts import ToolRunContext
from umbral.agent.tools.executor import ToolExecutor
from umbral.agent.tools.registry import ToolRegistry
from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.ports import ModelGateway
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.chat.service import ChatService
from umbral.application.playground.contracts import (
    ConversationRequest,
    ConversationTrace,
)
from umbral.infrastructure.agent.intent.contract_loader import load_intent_contract
from umbral.infrastructure.agent.model_gateway.managed import ManagedModelGateway
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract
from umbral.infrastructure.playground.fixtures import PlaygroundFixture, load_fixtures
from umbral.infrastructure.playground.in_memory import (
    FixedProfileStatusReader,
    InMemoryChatMessageRepository,
    InMemoryChatSessionRepository,
    InMemoryGraphRunRepository,
    LocalProfileState,
    LocalProposalDecisionGateway,
    LocalProposalRepository,
    LocalRadar,
    LocalScopeReader,
    NoopEventWriter,
    NoopPreferenceDecisionGateway,
    PlaygroundTraceCollector,
)
from umbral.infrastructure.playground.trace import event_record, primitive
from umbral.infrastructure.radar.contract_loader import load_events_registry

_USER_ID = UUID(int=1)
_REPLY_SCHEMA: dict[str, object] = {
    "reply_text": {"kind": "string", "min_length": 1, "max_length": 2000},
    "refs": {
        "kind": "list",
        "item": {"entity": "string", "id": "string"},
        "max_items": 10,
    },
    "tool_calls": {
        "kind": "list",
        "item": {"tool": "string", "args": "object"},
        "max_items": 5,
    },
}


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
                    "state": primitive(as_serializable(checkpoint)),
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
    registry = ToolRegistry(load_tool_contract)
    executor = ToolExecutor(
        registry=registry,
        implementations=_tool_implementations(
            profile_state=profile_state,
            fixture=fixture,
            proposals=proposals,
        ),
        recorder=recorder,
        scope_reader=LocalScopeReader(profile_state.profile_id, session.session_id),
        timeout_seconds=10,
        output_max_items=20,
    )
    graph = build_topology_v3(
        gateway=gateway,
        conversation=chat,
        recorder=recorder,
        saver=MemorySaver(),
        tool_executor=executor,
        intent_compiler=IntentCompiler(
            gateway=gateway,
            contract=load_intent_contract(),
            prompt_version="agent-intent-v1",
            model_version="local-fake"
            if model_mode == "fake"
            else os.getenv("AGENT_MODEL_NAME", "managed"),
        ),
        decision_gateway=LocalProposalDecisionGateway(proposals),
        preference_gateway=NoopPreferenceDecisionGateway(),
        clock=lambda: datetime.now(timezone.utc),
        model_version="local-fake"
        if model_mode == "fake"
        else os.getenv("AGENT_MODEL_NAME", "managed"),
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
    runs = InMemoryGraphRunRepository()
    runtime = ChatRuntime(
        graph=graph,
        conversation=chat,
        runs=runs,
        recorder=recorder,
        state_schema_version=CHAT_STATE_SCHEMA_VERSION,
        topology_version=CHAT_TOPOLOGY_VERSION,
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
        self.calls.append(
            {
                "prompt_version": prompt_version,
                "model_version": model_version,
                "schema_version": schema_version,
                "messages": messages,
                "tools": tools,
            }
        )
        if prompt_version == "agent-intent-v1":
            content: Mapping[str, object] = {
                "intent": "refinamiento",
                "parameters": [{"key": "budget", "value": "1000", "confidence": 0.98}],
                "high_impact_missing": [],
                "contradictions": [],
            }
        else:
            has_tool_results = any(item.get("role") == "tool" for item in messages)
            content = {
                "reply_text": (
                    "Listo, apliqué el cambio a tu radar."
                    if has_tool_results
                    else "Voy a proponer bajar el presupuesto a 1000."
                ),
                "refs": [],
                "tool_calls": []
                if has_tool_results
                else [
                    {
                        "tool": "propose_search_profile_update",
                        "args": {"change": {"budget": "1000"}},
                    }
                ],
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


def _tool_implementations(
    *,
    profile_state: LocalProfileState,
    fixture: PlaygroundFixture,
    proposals: SearchProfileUpdateProposals,
) -> dict[str, Any]:
    def get_profile(
        context: ToolRunContext, _args: Mapping[str, object]
    ) -> Mapping[str, object]:
        profile = profile_state.snapshot()
        return {
            "profile_id": str(context.search_profile_id),
            "state": profile.get("status", "active"),
            "snapshot": profile,
            "criteria": [],
        }

    def propose(
        context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        change = args.get("change")
        if not isinstance(change, Mapping):
            raise ValueError("change is required")
        proposal = proposals.propose(
            user_id=context.user_id,
            session_id=context.session_id,
            search_profile_id=context.search_profile_id,
            change=dict(change),
            correlation_id=context.correlation_id,
        )
        return {
            "proposal_id": str(proposal.proposal_id),
            "diff": dict(proposal.diff),
            "impact": dict(proposal.impact),
            "state": proposal.state,
            "expires_at": proposal.expires_at.isoformat(),
        }

    def apply(
        context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        result = proposals.apply(
            user_id=context.user_id,
            session_id=context.session_id,
            search_profile_id=context.search_profile_id,
            proposal_id=UUID(str(args["proposal_id"])),
            confirmation=bool(args["confirmation"]),
            idempotency_key=str(args["idempotency_key"]),
            correlation_id=context.correlation_id,
        )
        return {
            "proposal_id": str(result.proposal_id),
            "state": result.state,
            "profile_version": result.profile_version,
            "run_id": None,
        }

    def find_matches(
        _context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        limit = int(args.get("limit", 20))
        items = [
            {
                "item_id": str(item.get("uuid", item["id"])),
                "listing_id": str(item.get("uuid", item["id"])),
                "score": 0.82,
                "position": index + 1,
            }
            for index, item in enumerate(fixture.listings[:limit])
        ]
        return {
            "run_id": "00000000-0000-0000-0000-000000000201",
            "items": items,
            "total": len(items),
            "stale": False,
        }

    def detail(
        _context: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        listing = _listing_by_id(fixture, str(args["listing_id"]))
        return {
            "listing_id": str(listing.get("uuid", listing["id"])),
            "source_id": listing.get("source_id"),
            "neighborhood": listing.get("neighborhood"),
            "geo_precision": listing.get("geo_precision", "rooftop"),
            "total_cost": listing.get("total_cost"),
            "price_value": listing.get("price_value"),
            "price_currency": listing.get("price_currency"),
            "expenses_value": listing.get("expenses_value"),
            "surface_m2": listing.get("surface_m2"),
            "rooms": listing.get("rooms"),
            "bedrooms": listing.get("bedrooms"),
            "floor": listing.get("floor"),
            "property_type": listing.get("property_type"),
            "amenities": listing.get("amenities", []),
            "known_changes": [],
        }

    def urban(
        _context: ToolRunContext, _args: Mapping[str, object]
    ) -> Mapping[str, object]:
        return {"signals": [], "precision": "fixture"}

    return {
        "get_search_profile": get_profile,
        "propose_search_profile_update": propose,
        "apply_search_profile_update": apply,
        "find_matches": find_matches,
        "get_listing_detail": detail,
        "search_urban_context": urban,
    }


def _listing_by_id(fixture: PlaygroundFixture, listing_id: str) -> Mapping[str, object]:
    for listing in fixture.listings:
        if listing_id in {str(listing.get("id")), str(listing.get("uuid"))}:
            return listing
    raise ValueError("listing not found")


def _decision_from_text(text: str) -> dict[str, object] | None:
    normalized = " ".join(text.casefold().split())
    if re.search(r"\b(confirmo|confirmar|si|sí|aplicalo|aplícalo)\b", normalized):
        return {"kind": "approve", "idempotency_key": f"playground:{uuid4()}"}
    if re.search(r"\b(rechazo|rechazar|no|cancelalo|cancelarlo)\b", normalized):
        return {"kind": "reject", "reason": "playground"}
    return None


def _reply_from_checkpoint(state: Mapping[str, object]) -> str | None:
    context = state.get("context")
    if isinstance(context, Mapping):
        generated = context.get("generated_reply")
        if isinstance(generated, Mapping):
            return str(generated.get("text", "")) or None
    return None


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
            or "apply_search_profile_update" in tool_names,
            "value": {
                "before": before.get("budget_max"),
                "after": after.get("budget_max"),
            },
        },
    ]
