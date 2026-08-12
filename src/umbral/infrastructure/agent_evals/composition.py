"""Eval stack composition over the real v3 graph (research R-03/R-12).

The eval executor builds one fresh v3 stack per golden case with a
deterministic scripted gateway and injected tool implementations, runs every
turn through the real ``ChatRuntime`` (real checkpointer, recorder and chat
service) and records a behavioral trace. The gate runs this stack under the
deterministic adapter; the real-provider flow is a separate opt-in script.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import count
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from umbral.agent.graph import CHAT_TOPOLOGY_VERSION, build_topology_v3
from umbral.agent.intent.compiler import IntentCompiler
from umbral.agent.runtime import ChatRuntime, GraphLike
from umbral.agent.state import CHAT_STATE_SCHEMA_VERSION
from umbral.agent.tools.executor import ToolExecutor, ToolImplementation
from umbral.agent.tools.registry import ToolRegistry
from umbral.application.agent.ports import ModelGateway
from umbral.application.agent.service import RunRecorderService
from umbral.application.agent.tools.contracts import Proposal
from umbral.application.agent.tools.ports import ProposalDecisionGateway
from umbral.application.agent_evals.contracts import (
    CaseTrace,
    GoldenConversationCase,
    GraphRelease,
    ModelCallCostRecord,
    RecordedToolCall,
)
from umbral.application.chat.contracts import ChatSession
from umbral.application.chat.service import ChatService
from umbral.infrastructure.agent.checkpointer import create_postgres_saver
from umbral.infrastructure.agent.composition import chat_scope_reader
from umbral.infrastructure.agent.intent.contract_loader import load_intent_contract
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract
from umbral.infrastructure.agent_evals.scripted_gateway import (
    ScriptedModelGateway,
)
from umbral.infrastructure.db.models.agent import AgentModelCall, AgentNodeRun
from umbral.infrastructure.db.models.chat import ChatMessage
from umbral.infrastructure.db.repositories.agent import (
    SqlAlchemyGraphRunRepository,
    SqlAlchemyModelCallRepository,
    SqlAlchemyNodeRunRepository,
)
from umbral.infrastructure.db.repositories.chat import (
    SqlAlchemyChatMessageRepository,
    SqlAlchemyChatSessionRepository,
    SqlAlchemySearchProfileStatusReader,
)
from umbral.infrastructure.db.repositories.radar import SqlAlchemyEventRepository
from umbral.infrastructure.radar.contract_loader import load_events_registry

SessionFactory = Callable[[], Session]

_NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
_tick = count()

_REPLY_SCHEMA: Mapping[str, object] = {
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

_INTENT_TOOL_BY_FAMILY: Mapping[str, str] = {
    "onboarding": "consulta",
    "ambiguous_change": "refinamiento",
    "preferences": "refinamiento",
    "explanation": "consulta",
    "comparison": "comparacion",
    "feedback": "feedback",
    "injection": "fuera_de_alcance",
    "safe_refusal": "fuera_de_alcance",
}


def _advancing_clock() -> datetime:
    return _NOW + timedelta(seconds=next(_tick))


def _intent_response(case: GoldenConversationCase) -> Mapping[str, object]:
    if case.expectation.outcome == "clarification":
        return {
            "intent": "refinamiento",
            "parameters": [],
            "high_impact_missing": ["budget"],
            "contradictions": [],
        }
    if case.expectation.outcome == "safe_refusal":
        return {
            "intent": "fuera_de_alcance",
            "parameters": [],
            "high_impact_missing": [],
            "contradictions": [],
        }
    return {
        "intent": _INTENT_TOOL_BY_FAMILY.get(case.family, "consulta"),
        "parameters": [],
        "high_impact_missing": [],
        "contradictions": [],
    }


def _reply_sequence(case: GoldenConversationCase) -> list[Mapping[str, object]]:
    sequence: list[Mapping[str, object]] = []
    for call in case.expectation.tool_calls:
        sequence.append(
            {
                "reply_text": f"ejecuto {call.tool}",
                "refs": [],
                "tool_calls": [{"tool": call.tool, "args": dict(call.args)}],
            }
        )
    sequence.append(
        {
            "_final": True,
            "text": "respuesta final del caso",
            "require_refs": case.expectation.grounding.require_refs,
        }
    )
    return sequence


def _scripted_gateway(case: GoldenConversationCase) -> object:
    return ScriptedModelGateway(
        intent_response=_intent_response(case),
        reply_sequence=_reply_sequence(case),
        intent_prompt_version="agent-intent-v1",
        reply_prompt_version="agent-reply-v2",
    )


def default_tool_implementations() -> Mapping[str, ToolImplementation]:
    """Deterministic tool stubs consistent with the redacted result shapes the
    grounded persist path accepts (find_matches/explain_match/compare_listings
    return listing/evidence ids)."""
    import uuid as _uuid

    from umbral.agent.tools.contracts import ToolRunContext

    def get_search_profile(
        ctx: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        return {
            "profile_id": str(ctx.search_profile_id),
            "state": "active",
            "snapshot": {
                "operation": "rental",
                "zones": ["Palermo"],
                "budget_max": 900000,
                "min_rooms": 2,
            },
            "criteria": [
                {"key": "budget_max", "value": 900000},
                {"key": "zona", "value": "Palermo"},
                {"key": "min_rooms", "value": 2},
            ],
        }

    def find_matches(
        ctx: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        listing_id = _uuid.uuid5(_uuid.NAMESPACE_OID, f"{ctx.search_profile_id}")
        return {
            "run_id": str(ctx.run_id),
            "items": [{"listing_id": str(listing_id)}],
            "total": 1,
            "stale": False,
        }

    def explain_match(
        ctx: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        listing_id = _uuid.uuid5(_uuid.NAMESPACE_OID, f"{ctx.search_profile_id}")
        return {
            "listing_id": str(listing_id),
            "explanation": {"summary": "criterios cumplidos"},
            "evidence_refs": [
                {"id": str(_uuid.uuid5(_uuid.NAMESPACE_OID, "evidence-1"))}
            ],
        }

    def get_listing_detail(
        ctx: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        listing_id = _uuid.uuid5(_uuid.NAMESPACE_OID, f"{ctx.search_profile_id}")
        return {
            "listing_id": str(listing_id),
            "neighborhood": "Palermo",
            "total_cost": 900000,
            "price_value": 900000,
            "price_currency": "ARS",
            "surface_m2": 55,
            "rooms": 2,
            "property_type": "departamento",
        }

    def compare_listings(
        ctx: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        listing_id = _uuid.uuid5(_uuid.NAMESPACE_OID, f"{ctx.search_profile_id}")
        return {"cells": [{"listing_id": str(listing_id)}]}

    def record_feedback(
        ctx: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        return {"feedback_event_id": str(_uuid.uuid4())}

    def propose_search_profile_update(
        ctx: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        return {
            "proposal_id": str(_uuid.uuid4()),
            "state": "pending",
            "diff": {"change": dict(args)},
            "impact": {"recompute": True},
        }

    def propose_search_preference_update(
        ctx: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        return {
            "proposal_id": str(_uuid.uuid4()),
            "state": "pending",
            "diff": {"concept_key": "luminosidad", "polarity": "positive"},
            "impact": {"concept_key": "luminosidad", "polarity": "positive"},
            "expires_at": "2026-08-11T12:00:00+00:00",
        }

    def apply_search_profile_update(
        ctx: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        raise AssertionError("eval cases never apply")

    def search_urban_context(
        ctx: ToolRunContext, args: Mapping[str, object]
    ) -> Mapping[str, object]:
        return {"signals": []}

    return {
        "get_search_profile": get_search_profile,
        "find_matches": find_matches,
        "explain_match": explain_match,
        "get_listing_detail": get_listing_detail,
        "compare_listings": compare_listings,
        "record_feedback": record_feedback,
        "propose_search_profile_update": propose_search_profile_update,
        "propose_search_preference_update": propose_search_preference_update,
        "apply_search_profile_update": apply_search_profile_update,
        "search_urban_context": search_urban_context,
    }


class _NoOpDecisionGateway:
    """Eval cases never reach a HITL proposal decision (0 propose in golden)."""

    def get(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        proposal_id: UUID,
    ) -> Proposal:
        raise AssertionError("eval cases never require a proposal decision")

    def reject(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        proposal_id: UUID,
        note: str,
        correlation_id: UUID,
    ) -> Proposal:
        raise AssertionError("eval cases never require a proposal decision")

    def derive(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        proposal_id: UUID,
        change: Mapping[str, object],
        correlation_id: UUID,
    ) -> Proposal:
        raise AssertionError("eval cases never require a proposal decision")


class _NoOpPreferenceGateway:
    """Eval cases never reach a HITL preference decision."""

    def get_proposal(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        proposal_id: UUID,
    ) -> object:
        raise AssertionError("eval cases never require a preference decision")

    def confirm_proposal(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        proposal_id: UUID,
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> object:
        raise AssertionError("eval cases never require a preference decision")

    def confirm_preference_removal(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        proposal_id: UUID,
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> object:
        raise AssertionError("eval cases never require a preference decision")

    def reject_proposal(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        proposal_id: UUID,
        correlation_id: UUID,
        actor_id: str | None = None,
    ) -> object:
        raise AssertionError("eval cases never require a preference decision")


@dataclass(frozen=True, slots=True)
class EvalStack:
    runtime: ChatRuntime
    chat: ChatService
    runs: SqlAlchemyGraphRunRepository
    factory: SessionFactory


class PostgresEvalCaseExecutor:
    """Drives every golden case through a fresh real v3 stack (R-03).

    ``gateway_factory`` swaps the deterministic scripted gateway for the
    real-provider flow (opt-in, Q4); the default builds a scripted gateway per
    case.
    """

    def __init__(
        self,
        *,
        factory: SessionFactory,
        url: str,
        seed_user: Callable[[SessionFactory], UUID],
        seed_profile: Callable[[SessionFactory, UUID], object],
        tool_implementations: Mapping[str, ToolImplementation] | None = None,
        gateway_factory: Callable[[GoldenConversationCase], object] | None = None,
        contexts: Mapping[str, Mapping[str, object]] | None = None,
    ) -> None:
        self.factory = factory
        self.url = url
        self.tool_implementations = (
            tool_implementations or default_tool_implementations()
        )
        self.gateway_factory = gateway_factory or _scripted_gateway
        self.seed_user = seed_user
        self.seed_profile = seed_profile
        self.contexts = contexts or {}

    def execute(
        self, *, case: GoldenConversationCase, release: GraphRelease
    ) -> CaseTrace:
        stack = self._build_stack(
            case, model_version=release.components.model_version
        )
        user_id = self.seed_user(self.factory)
        profile = self.seed_profile(self.factory, user_id)
        session = stack.chat.create_session(
            user_id=user_id,
            search_profile_id=cast("UUID", getattr(profile, "profile_id")),
            correlation_id=uuid4(),
        )
        return _run_case(
            stack=stack,
            case=case,
            user_id=user_id,
            session=session,
            user_context=self.contexts.get(case.id),
        )

    def _build_stack(
        self, case: GoldenConversationCase, *, model_version: str
    ) -> EvalStack:
        chat = ChatService(
            sessions=SqlAlchemyChatSessionRepository(self.factory),
            messages=SqlAlchemyChatMessageRepository(self.factory),
            profile_status=SqlAlchemySearchProfileStatusReader(self.factory),
            events_out=SqlAlchemyEventRepository(self.factory),
            events_registry=load_events_registry(),
            max_message_length=4000,
            clock=_advancing_clock,
        )
        runs = SqlAlchemyGraphRunRepository(self.factory)
        recorder = RunRecorderService(
            graph_runs=runs,
            node_runs=SqlAlchemyNodeRunRepository(self.factory),
            model_calls=SqlAlchemyModelCallRepository(self.factory),
        )
        gateway = self.gateway_factory(case)
        intent_compiler = IntentCompiler(
            gateway=cast("ModelGateway", gateway),
            contract=load_intent_contract(),
            prompt_version="agent-intent-v1",
            model_version=model_version,
        )
        executor = ToolExecutor(
            registry=ToolRegistry(load_tool_contract),
            implementations=self.tool_implementations,
            recorder=recorder,
            scope_reader=chat_scope_reader(chat),
            timeout_seconds=10.0,
        )
        saver = create_postgres_saver(self.url, strict_msgpack=True)
        graph = build_topology_v3(
            gateway=cast("ModelGateway", gateway),
            conversation=chat,
            recorder=recorder,
            saver=saver,
            tool_executor=executor,
            intent_compiler=intent_compiler,
            decision_gateway=cast(ProposalDecisionGateway, _NoOpDecisionGateway()),
            preference_gateway=_NoOpPreferenceGateway(),
            clock=_advancing_clock,
            model_version=model_version,
            prompt_version="agent-reply-v2",
            schema_version="reply-v3",
            reply_schema=_REPLY_SCHEMA,
            max_calls_per_turn=5,
            high_impact_keys=("budget", "zone", "hard_filters", "radio"),
            clarification_min_confidence=0.6,
            clarification_max_rounds=2,
            reply_chunk_words=8,
            reply_max_refs=10,
        )
        runtime = ChatRuntime(
            graph=cast("GraphLike", graph),
            conversation=chat,
            runs=runs,
            recorder=recorder,
            clock=_advancing_clock,
            state_schema_version=CHAT_STATE_SCHEMA_VERSION,
            topology_version=CHAT_TOPOLOGY_VERSION,
        )
        return EvalStack(runtime=runtime, chat=chat, runs=runs, factory=self.factory)


def _run_case(
    *,
    stack: EvalStack,
    case: GoldenConversationCase,
    user_id: UUID,
    session: ChatSession,
    user_context: Mapping[str, object] | None = None,
) -> CaseTrace:
    final_intent: str | None = None
    clarification_pending = False
    latency = 0
    run_status = "completed"
    run_id: UUID | None = None
    for turn in case.turns:
        outcome = stack.runtime.run_turn(
            user_id=user_id,
            session_id=session.session_id,
            text=turn,
            correlation_id=uuid4(),
            context=user_context,
        )
        run_id = outcome.run_id
        run_status = outcome.status
        latency += outcome.latency_ms or 0
        values = stack.runtime.graph.compiled.get_state(
            {"configurable": {"thread_id": str(outcome.run_id)}}
        ).values
        intent_data = values.get("intent")
        if isinstance(intent_data, Mapping):
            final_intent = str(intent_data.get("intent") or "")
        clarification = values.get("clarification")
        if isinstance(clarification, Mapping):
            clarification_pending = True
    assert run_id is not None
    tool_calls: list[RecordedToolCall] = []
    model_calls: list[ModelCallCostRecord] = []
    refs: list[dict[str, object]] = []
    with stack.factory() as db:
        tool_rows = db.execute(
            select(
                AgentNodeRun.node_name,
                AgentNodeRun.status,
                AgentNodeRun.error_summary,
            )
            .where(
                AgentNodeRun.graph_run_id == run_id,
                AgentNodeRun.node_kind == "tool",
            )
            .order_by(AgentNodeRun.started_at)
        ).all()
        for tool_row in tool_rows:
            error_summary = tool_row[2] if isinstance(tool_row[2], dict) else None
            tool_calls.append(
                RecordedToolCall(
                    name=tool_row[0],
                    status=tool_row[1],
                    error_code=(
                        str(error_summary.get("code")) if error_summary else None
                    ),
                )
            )
        model_rows = db.execute(
            select(
                AgentModelCall.model_version,
                AgentModelCall.input_tokens,
                AgentModelCall.output_tokens,
            ).where(AgentModelCall.graph_run_id == run_id)
        ).all()
        for model_row in model_rows:
            model_calls.append(
                ModelCallCostRecord(
                    model_version=model_row[0],
                    input_tokens=int(model_row[1] or 0),
                    output_tokens=int(model_row[2] or 0),
                )
            )
        message_rows = db.execute(
            select(ChatMessage.content).where(
                ChatMessage.graph_run_id == run_id,
                ChatMessage.role == "assistant",
            )
        ).all()
        for (content,) in message_rows:
            if isinstance(content, dict):
                for ref in content.get("refs", []):
                    if isinstance(ref, dict):
                        refs.append(ref)
    return CaseTrace(
        case_id=case.id,
        run_status=run_status,
        intent=final_intent,
        clarification_pending=clarification_pending,
        tool_calls=tuple(tool_calls),
        model_calls=tuple(model_calls),
        latency_ms=latency,
        refs=tuple(refs),
        allowed_ref_ids=_allowed_ref_ids(user_context, session.search_profile_id),
    )


def _allowed_ref_ids(
    user_context: Mapping[str, object] | None,
    profile_id: UUID,
) -> frozenset[tuple[str, str]]:
    """Ids the reply may legitimately cite: declared context objects plus the
    deterministic ids the eval tool stubs return for this profile."""
    import uuid as _uuid

    allowed: set[tuple[str, str]] = set()
    if isinstance(user_context, Mapping):
        entity = str(user_context.get("entity", ""))
        context_id = user_context.get("id")
        if entity == "listing" and isinstance(context_id, str):
            allowed.add(("listing", context_id))
        listing_ids = user_context.get("listing_ids")
        if isinstance(listing_ids, list):
            for listing_id in listing_ids:
                if isinstance(listing_id, str):
                    allowed.add(("listing", listing_id))
    stub_listing = str(_uuid.uuid5(_uuid.NAMESPACE_OID, f"{profile_id}"))
    allowed.add(("listing", stub_listing))
    allowed.add(("evidence_ref", str(_uuid.uuid5(_uuid.NAMESPACE_OID, "evidence-1"))))
    return frozenset(allowed)
