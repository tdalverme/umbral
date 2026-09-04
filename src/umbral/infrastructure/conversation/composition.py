"""V5 conversation composition over explicit application services.

Wires the V5 turn module and graph over the existing services: authorized
context assembly, typed interpretation, deterministic policy, command
execution, pending resolution, receipts, reply composition, and the separate
V5 graph. No V4 composition is touched here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from umbral.agent.graph import GraphDeps, build_graph
from umbral.agent.intent import InterpretationCompiler
from umbral.application.agent.ports import ModelGateway
from umbral.application.agent.tools.proposals import (
    SearchProfileUpdateProposals,
)
from umbral.application.chat.service import ChatService
from umbral.application.conversation.policy import plan_turn
from umbral.application.conversation.ports import (
    FeedbackRecorder,
    FocusedEntityReader,
    Interpreter,
    TurnAuditWriter,
)
from umbral.application.conversation.receipts import (
    CommandReceiptStore,
    InMemoryCommandReceiptStore,
)
from umbral.application.conversation.reply import ReplyComposer
from umbral.application.conversation.service import ConversationTurn
from umbral.application.preferences.intensity import IntensityPolicy
from umbral.application.preferences.ports import ConceptReader
from umbral.application.radar.service import RadarService
from umbral.infrastructure.conversation.context import (
    ContextAssembler,
    ProposalsPendingReader,
)
from umbral.infrastructure.conversation.executor import (
    EffectExecutor,
    ProposalsPendingResolver,
)
from umbral.infrastructure.conversation.preferences import PreferenceServiceLike

Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class ConversationServices:
    """The explicit services the V5 stack may read from and mutate through."""

    chat: ChatService
    radar: RadarService
    proposals: SearchProfileUpdateProposals
    preferences: PreferenceServiceLike | None = None
    feedback: FeedbackRecorder | None = None
    concepts: ConceptReader | None = None
    intensity_policy: IntensityPolicy | None = None
    concept_catalog: tuple[Mapping[str, object], ...] = ()


def build_conversation_turn_service(
    *,
    services: ConversationServices,
    focus: FocusedEntityReader,
    interpreter: Interpreter,
    receipts: CommandReceiptStore | None = None,
    audit: TurnAuditWriter | None = None,
    clock: Clock | None = None,
) -> ConversationTurn:
    """Assemble the V5 turn module over the explicit services."""
    clock = clock or (lambda: datetime.now(timezone.utc))
    pending_reader = ProposalsPendingReader(proposals=services.proposals)
    contexts = ContextAssembler(
        chat=services.chat,
        radar=services.radar,
        preferences=services.preferences,
        pending=pending_reader,
        focus=focus,
        clock=clock,
    )
    executor = EffectExecutor(
        radar=services.radar,
        chat=services.chat,
        proposals=services.proposals,
        preferences=services.preferences,
        feedback=services.feedback,
        concepts=services.concepts,
        intensity_policy=services.intensity_policy,
    )
    return ConversationTurn(
        contexts=contexts,
        interpreter=interpreter,
        policy=plan_turn,
        executor=executor,
        pending=ProposalsPendingResolver(proposals=services.proposals),
        receipts=receipts or InMemoryCommandReceiptStore(),
        audit=audit,
        clock=clock,
    )


def build_conversation_graph(
    *,
    services: ConversationServices,
    focus: FocusedEntityReader,
    gateway: ModelGateway,
    interpretation_schema: Mapping[str, object],
    reply_schema: Mapping[str, object],
    model_version: str = "gpt-4.1-mini",
    prompt_version: str = "interpretation",
    reply_prompt_version: str = "reply",
    receipts: CommandReceiptStore | None = None,
    audit: TurnAuditWriter | None = None,
    checkpointer: object | None = None,
    clock: Clock | None = None,
) -> object:
    """Compose the V5 graph over the explicit services."""
    interpreter = InterpretationCompiler(
        gateway=gateway,
        schema=interpretation_schema,
        prompt_version=prompt_version,
        model_version=model_version,
        concept_catalog=services.concept_catalog,
    )
    turn = build_conversation_turn_service(
        services=services,
        focus=focus,
        interpreter=interpreter,
        receipts=receipts,
        audit=audit,
        clock=clock,
    )
    reply = ReplyComposer(
        gateway=gateway,
        schema=reply_schema,
        prompt_version=reply_prompt_version,
        model_version=model_version,
    )
    return build_graph(
        dependencies=GraphDeps(turn=turn, reply=reply),
        checkpointer=checkpointer,
    )
