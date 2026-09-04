"""Production wiring of the single semantic conversation stack.

Composes the unversioned agent graph (typed interpretation, deterministic
policy, catalog-backed execution, ordered hard-filter confirmation) over the
real application services, durable receipts, Postgres checkpointer and the
managed model gateway for the API process.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from sqlalchemy.orm import Session

from umbral.application.agent.ports import ModelGateway
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.chat.service import ChatService
from umbral.application.radar.service import RadarService
from umbral.infrastructure.agent.checkpointer import create_postgres_saver
from umbral.infrastructure.agent.model_gateway.managed import ManagedModelGateway
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.conversation.preferences import PreferenceServiceLike
from umbral.infrastructure.db.repositories.agent import (
    SqlAlchemyGraphRunRepository,
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


@dataclass(frozen=True, slots=True)
class ProductionStack:
    """The conversation wiring ready for the chat router."""

    chat: ChatService
    graph: object
    turn: object
    proposals: SearchProfileUpdateProposals
    receipts: object
    graph_runs: SqlAlchemyGraphRunRepository


def build_production_stack(
    *,
    settings: Settings,
    session_factory: SessionFactory,
    database_url: str,
    radar: object,
    scoring: object,
    feedback: object,
    criteria: object,
) -> ProductionStack:
    """Compose the single graph stack over the real services."""
    del scoring, criteria
    from umbral.application.conversation.ports import (
        FeedbackRecorder,
        FocusedListing,
        Interpreter,
    )
    from umbral.infrastructure.conversation.composition import (
        ConversationServices,
        build_conversation_graph,
        build_conversation_turn_service,
    )
    from umbral.infrastructure.db.repositories.conversation_v5 import (
        SqlAlchemyCommandReceiptStore,
    )

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
    proposals = SearchProfileUpdateProposals(
        repository=SqlAlchemyProposalRepository(session_factory),
        radar=radar,  # type: ignore[arg-type]
        events=events_out,
        events_registry=events_registry,
        ttl_hours=settings.agent_proposal_ttl_hours,
        clock=clock,
        waiting_runs=runs,
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

    class _NoFocusReader:
        def verified_focus(
            self, *, user_id: object, session_id: object
        ) -> FocusedListing | None:
            return None

    contracts_dir = Path(__file__).parents[4] / "contracts" / "agent"
    interpretation_schema = json.loads(
        (contracts_dir / "interpretation-schema.json").read_text(encoding="utf-8")
    )
    reply_schema = json.loads(
        (contracts_dir / "reply-schema.json").read_text(encoding="utf-8")
    )
    preferences = _build_preference_service(session_factory)
    concept_catalog = _build_concept_catalog(session_factory)
    interpreter = _build_interpreter(
        gateway=gateway,
        schema=interpretation_schema,
        prompt_version="interpretation",
        model_version=settings.agent_model_name,
        concept_catalog=concept_catalog,
    )
    from umbral.application.preferences.intensity import load_intensity_policy

    services = ConversationServices(
        chat=chat,
        radar=cast(RadarService, radar),
        proposals=proposals,
        preferences=preferences,
        feedback=cast(FeedbackRecorder, feedback),
        concepts=getattr(preferences, "concepts", None),
        intensity_policy=load_intensity_policy(),
        concept_catalog=concept_catalog,
    )
    turn_service = build_conversation_turn_service(
        services=services,
        focus=_NoFocusReader(),
        interpreter=cast(Interpreter, interpreter),
        receipts=SqlAlchemyCommandReceiptStore(session_factory),
        clock=clock,
    )
    saver = create_postgres_saver(
        database_url, strict_msgpack=settings.agent_strict_msgpack
    )
    graph = build_conversation_graph(
        services=services,
        focus=_NoFocusReader(),
        gateway=gateway,
        interpretation_schema=interpretation_schema,
        reply_schema=reply_schema,
        model_version=settings.agent_model_name,
        prompt_version="interpretation",
        reply_prompt_version="reply",
        receipts=SqlAlchemyCommandReceiptStore(session_factory),
        checkpointer=saver,
        clock=clock,
    )
    return ProductionStack(
        chat=chat,
        graph=graph,
        turn=turn_service,
        proposals=proposals,
        receipts=SqlAlchemyCommandReceiptStore(session_factory),
        graph_runs=runs,
    )


def _build_interpreter(
    *,
    gateway: ModelGateway,
    schema: Mapping[str, object],
    prompt_version: str,
    model_version: str,
    concept_catalog: tuple[Mapping[str, object], ...],
) -> object:
    from umbral.agent.intent import InterpretationCompiler

    return InterpretationCompiler(
        gateway=gateway,
        schema=schema,
        prompt_version=prompt_version,
        model_version=model_version,
        concept_catalog=concept_catalog,
    )


def _build_concept_catalog(
    session_factory: SessionFactory,
) -> tuple[Mapping[str, object], ...]:
    """Snapshot the published concept registry for one interpreter."""
    from umbral.infrastructure.db.repositories.criteria import (
        SqlAlchemyConceptRepository,
    )

    catalog = tuple(
        {
            "key": concept.key,
            "description": concept.name,
            "matcher_type": concept.matcher_type,
            "computable": bool(concept.compute_policy.get("computable", False)),
            "aliases": list(concept.aliases),
        }
        for concept in SqlAlchemyConceptRepository(session_factory).list_active()
    )
    if not catalog:
        raise ValueError("active concept registry is empty")
    return catalog


def _build_preference_service(session_factory: SessionFactory) -> PreferenceServiceLike:
    from umbral.application.preferences.contracts import (
        PreferenceConcept,
        PreferencePolicySpec,
    )
    from umbral.application.preferences.service import PreferenceService
    from umbral.infrastructure.db.repositories.criteria import (
        SqlAlchemyConceptRepository,
    )
    from umbral.infrastructure.db.repositories.preferences import (
        SqlAlchemyBindingRepository,
        SqlAlchemyExpressionRepository,
    )

    expressions = SqlAlchemyExpressionRepository(session_factory)
    bindings = SqlAlchemyBindingRepository(session_factory)
    concepts = SqlAlchemyConceptRepository(session_factory)

    class _ConceptReader:
        def get(self, key: str) -> PreferenceConcept | None:
            concept = concepts.get(key)
            if concept is None:
                return None
            return PreferenceConcept(
                key=concept.key,
                matcher_type=concept.matcher_type,
                computable=bool(
                    (concept.compute_policy or {}).get("computable", False)
                ),
            )

    return PreferenceService(
        expressions=expressions,
        bindings=bindings,
        mutations=expressions,
        concepts=_ConceptReader(),
        policy=PreferencePolicySpec.v1(),
    )
