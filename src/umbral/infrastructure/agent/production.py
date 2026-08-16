"""Production wiring of the conversational agent runtime (H4.4 deferral).

Composes the v3 agent stack (topology v3, intent compiler, tool executor over
the real application services, durable proposals, Postgres checkpointer and
the managed model gateway) for the API process. The router only depends on
the four exposed objects (chat, runtime, proposals, graph_runs). A second
builder composes the v4 copilot stack (feature 016) for the same surface.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

from sqlalchemy.orm import Session

from umbral.agent.graph import (
    CHAT_TOPOLOGY_VERSION,
    COPILOT_TOPOLOGY_VERSION,
    build_topology_v3,
    build_topology_v4,
)
from umbral.agent.intent.compiler import IntentCompiler
from umbral.agent.intent.interpretation import InterpretationCompiler
from umbral.agent.runtime import ChatRuntime, GraphLike
from umbral.agent.state import (
    CHAT_STATE_SCHEMA_VERSION,
    COPILOT_STATE_SCHEMA_VERSION,
)
from umbral.agent.tools.executor import ToolExecutor
from umbral.agent.tools.registry import ToolRegistry
from umbral.agent.tools.tools import ToolServices, build_tool_implementations
from umbral.application.agent.ports import ModelGateway
from umbral.application.agent.service import RunRecorderService
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.chat.service import ChatService
from umbral.application.radar.service import RadarService
from umbral.infrastructure.agent.checkpointer import create_postgres_saver
from umbral.infrastructure.agent.composition import chat_scope_reader
from umbral.infrastructure.agent.intent.contract_loader import load_intent_contract
from umbral.infrastructure.agent.intent.interpretation_loader import (
    load_interpretation_schema,
)
from umbral.infrastructure.agent.model_gateway.managed import ManagedModelGateway
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract
from umbral.infrastructure.agent.tools.preferences_loader import (
    load_preference_vocabulary,
)
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.conversation.composition import (
    CopilotServices,
    build_conversation_turn_service,
)
from umbral.infrastructure.db.repositories.agent import (
    SqlAlchemyGraphRunRepository,
    SqlAlchemyModelCallRepository,
    SqlAlchemyNodeRunRepository,
    SqlAlchemyProposalRepository,
)
from umbral.infrastructure.db.repositories.chat import (
    SqlAlchemyChatMessageRepository,
    SqlAlchemyChatSessionRepository,
    SqlAlchemySearchProfileStatusReader,
)
from umbral.infrastructure.db.repositories.radar import SqlAlchemyEventRepository
from umbral.infrastructure.radar.contract_loader import load_events_registry

SessionFactory = Callable[[], Session]

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

_HIGH_IMPACT_KEYS = ("budget", "zona", "hard_filters", "radio")


@dataclass(frozen=True, slots=True)
class ProductionAgentStack:
    """The objects the chat router consumes."""

    chat: ChatService
    runtime: ChatRuntime
    proposals: SearchProfileUpdateProposals
    graph_runs: SqlAlchemyGraphRunRepository


def build_production_agent_stack(
    *,
    settings: Settings,
    session_factory: SessionFactory,
    database_url: str,
    radar: object,
    scoring: object,
    feedback: object,
    criteria: object,
) -> ProductionAgentStack:
    """Compose the v3 stack over the real services and managed gateway."""
    events_out = SqlAlchemyEventRepository(session_factory)
    events_registry = load_events_registry()

    def clock() -> datetime:
        return datetime.now(timezone.utc)

    chat = ChatService(
        sessions=SqlAlchemyChatSessionRepository(session_factory),
        messages=SqlAlchemyChatMessageRepository(session_factory),
        profile_status=SqlAlchemySearchProfileStatusReader(session_factory),
        events_out=events_out,
        events_registry=events_registry,
        max_message_length=settings.chat_message_max_length,
        clock=clock,
    )
    runs = SqlAlchemyGraphRunRepository(session_factory)
    recorder = RunRecorderService(
        graph_runs=runs,
        node_runs=SqlAlchemyNodeRunRepository(session_factory),
        model_calls=SqlAlchemyModelCallRepository(session_factory),
    )
    proposals = SearchProfileUpdateProposals(
        repository=SqlAlchemyProposalRepository(session_factory),
        radar=radar,  # type: ignore[arg-type]
        events=events_out,
        events_registry=events_registry,
        ttl_hours=settings.agent_proposal_ttl_hours,
        clock=clock,
    )
    if settings.agent_model_provider == "managed" and settings.agent_managed_endpoint:
        gateway: ModelGateway = ManagedModelGateway(
            endpoint=settings.agent_managed_endpoint,
            api_key=settings.agent_managed_api_key or "",
            model=settings.agent_model_name,
            timeout_seconds=settings.agent_model_timeout_seconds,
            max_retries=settings.agent_model_max_retries,
        )
    else:
        from umbral.infrastructure.agent.model_gateway.fake import FakeModelGateway

        gateway = cast(
            ModelGateway,
            FakeModelGateway(model_version=settings.agent_model_name),
        )

    intent_compiler = IntentCompiler(
        gateway=gateway,
        contract=load_intent_contract(),
        prompt_version=settings.agent_intent_prompt_version,
        model_version=settings.agent_model_name,
    )
    executor = ToolExecutor(
        registry=ToolRegistry(load_tool_contract),
        implementations=build_tool_implementations(
            ToolServices(
                radar=radar,  # type: ignore[arg-type]
                scoring=scoring,  # type: ignore[arg-type]
                feedback=feedback,  # type: ignore[arg-type]
                criteria=criteria,  # type: ignore[arg-type]
                proposals=proposals,
                vocabulary=load_preference_vocabulary(),
            )
        ),
        recorder=recorder,
        scope_reader=chat_scope_reader(chat),
        timeout_seconds=settings.agent_tools_timeout_seconds,
        output_max_items=settings.agent_tools_output_max_items,
    )
    saver = create_postgres_saver(
        database_url, strict_msgpack=settings.agent_strict_msgpack
    )
    graph = cast("GraphLike", build_topology_v3(
        gateway=gateway,
        conversation=chat,
        recorder=recorder,
        saver=saver,
        tool_executor=executor,
        intent_compiler=intent_compiler,
        decision_gateway=proposals,
        preference_gateway=feedback,  # type: ignore[arg-type]
        clock=clock,
        model_version=settings.agent_model_name,
        prompt_version=settings.agent_reply_prompt_version,
        schema_version="reply-v3",
        reply_schema=_REPLY_SCHEMA,
        max_calls_per_turn=settings.agent_tools_max_calls_per_turn,
        high_impact_keys=_HIGH_IMPACT_KEYS,
        clarification_min_confidence=settings.agent_clarification_min_confidence,
        clarification_max_rounds=settings.agent_clarification_max_rounds,
        reply_chunk_words=settings.agent_reply_chunk_words,
        reply_max_refs=settings.agent_reply_max_refs,
    ))
    runtime = ChatRuntime(
        graph=graph,
        conversation=chat,
        runs=runs,
        recorder=recorder,
        clock=clock,
        state_schema_version=CHAT_STATE_SCHEMA_VERSION,
        topology_version=CHAT_TOPOLOGY_VERSION,
        release_id=settings.agent_graph_release_id,
    )
    return ProductionAgentStack(
        chat=chat, runtime=runtime, proposals=proposals, graph_runs=runs
    )


def build_production_copilot_stack(
    *,
    settings: Settings,
    session_factory: SessionFactory,
    database_url: str,
    radar: object,
    scoring: object,
    feedback: object,
    criteria: object,
) -> ProductionAgentStack:
    """Compose the v4 copilot stack over the real services (feature 016).

    The v4 topology replaces the intent/tool loop with the deterministic turn
    orchestrator: verified context -> ordered acts -> planned effects -> safe
    application -> refresh/confirmation. Ranking and hard filters stay in the
    explicit services; the model only fills the reply and the acts.
    """
    events_out = SqlAlchemyEventRepository(session_factory)
    events_registry = load_events_registry()

    def clock() -> datetime:
        return datetime.now(timezone.utc)

    chat = ChatService(
        sessions=SqlAlchemyChatSessionRepository(session_factory),
        messages=SqlAlchemyChatMessageRepository(session_factory),
        profile_status=SqlAlchemySearchProfileStatusReader(session_factory),
        events_out=events_out,
        events_registry=events_registry,
        max_message_length=settings.chat_message_max_length,
        clock=clock,
    )
    runs = SqlAlchemyGraphRunRepository(session_factory)
    recorder = RunRecorderService(
        graph_runs=runs,
        node_runs=SqlAlchemyNodeRunRepository(session_factory),
        model_calls=SqlAlchemyModelCallRepository(session_factory),
    )
    proposals = SearchProfileUpdateProposals(
        repository=SqlAlchemyProposalRepository(session_factory),
        radar=radar,  # type: ignore[arg-type]
        events=events_out,
        events_registry=events_registry,
        ttl_hours=settings.agent_proposal_ttl_hours,
        clock=clock,
    )
    if settings.agent_model_provider == "managed" and settings.agent_managed_endpoint:
        gateway: ModelGateway = ManagedModelGateway(
            endpoint=settings.agent_managed_endpoint,
            api_key=settings.agent_managed_api_key or "",
            model=settings.agent_model_name,
            timeout_seconds=settings.agent_model_timeout_seconds,
            max_retries=settings.agent_model_max_retries,
        )
    else:
        from umbral.infrastructure.agent.model_gateway.fake import FakeModelGateway

        gateway = cast(
            ModelGateway,
            FakeModelGateway(model_version=settings.agent_model_name),
        )

    interpretation_compiler = InterpretationCompiler(
        gateway=gateway,
        schema=load_interpretation_schema(),
        prompt_version=settings.agent_intent_prompt_version,
        model_version=settings.agent_model_name,
    )
    turn_service = build_conversation_turn_service(
        services=CopilotServices(chat=chat, radar=cast(RadarService, radar)),
        proposals=proposals,
        interpretation=interpretation_compiler,
        clock=clock,
    )
    saver = create_postgres_saver(
        database_url, strict_msgpack=settings.agent_strict_msgpack
    )
    graph = cast("GraphLike", build_topology_v4(
        gateway=gateway,
        conversation=chat,
        recorder=recorder,
        saver=saver,
        turn_service=turn_service,
        interpretation=interpretation_compiler,
        clock=clock,
        model_version=settings.agent_model_name,
        prompt_version=settings.agent_reply_prompt_version,
        schema_version="reply-v4",
        reply_schema=_COPILOT_REPLY_SCHEMA,
        reply_chunk_words=settings.agent_reply_chunk_words,
        reply_max_refs=settings.agent_reply_max_refs,
    ))
    runtime = ChatRuntime(
        graph=graph,
        conversation=chat,
        runs=runs,
        recorder=recorder,
        clock=clock,
        state_schema_version=COPILOT_STATE_SCHEMA_VERSION,
        topology_version=COPILOT_TOPOLOGY_VERSION,
        release_id=settings.agent_graph_release_id,
    )
    return ProductionAgentStack(
        chat=chat, runtime=runtime, proposals=proposals, graph_runs=runs
    )


_COPILOT_REPLY_SCHEMA: dict[str, object] = {
    "reply_text": {"kind": "string", "min_length": 1, "max_length": 2000},
    "effects": {
        "kind": "list",
        "item": {
            "act_id": "string",
            "status": {"enum": ["applied", "pending", "remembered", "rejected"]},
        },
        "max_items": 10,
    },
    "question": {"kind": "nullable_string"},
    "refs": {
        "kind": "list",
        "item": {"entity": "string", "id": "string"},
        "max_items": 10,
    },
}
