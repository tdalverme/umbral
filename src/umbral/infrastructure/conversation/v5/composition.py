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

from umbral.agent.graph_v5 import GraphDepsV5, build_graph_v5
from umbral.agent.intent.v5 import InterpretationCompilerV5
from umbral.application.agent.ports import ModelGateway
from umbral.application.agent.tools.proposals import (
    SearchProfileUpdateProposals,
)
from umbral.application.chat.service import ChatService
from umbral.application.conversation.v5.policy import plan_turn_v5
from umbral.application.conversation.v5.ports import (
    FeedbackRecorderV5,
    FocusedEntityReader,
    InterpreterV5,
    TurnAuditWriterV5,
)
from umbral.application.conversation.v5.receipts import (
    CommandReceiptStore,
    InMemoryCommandReceiptStore,
)
from umbral.application.conversation.v5.reply import ReplyComposerV5
from umbral.application.conversation.v5.service import ConversationTurnV5
from umbral.application.preferences.intensity import IntensityPolicy
from umbral.application.preferences.ports import ConceptReader
from umbral.application.radar.service import RadarService
from umbral.infrastructure.conversation.composition import PreferenceServiceLike
from umbral.infrastructure.conversation.v5.context import (
    ContextAssemblerV5,
    ProposalsPendingReaderV5,
)
from umbral.infrastructure.conversation.v5.executor import (
    EffectExecutorV5,
    ProposalsPendingResolverV5,
)

Clock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class V5Services:
    """The explicit services the V5 stack may read from and mutate through."""

    chat: ChatService
    radar: RadarService
    proposals: SearchProfileUpdateProposals
    preferences: PreferenceServiceLike | None = None
    feedback: FeedbackRecorderV5 | None = None
    concepts: ConceptReader | None = None
    intensity_policy: IntensityPolicy | None = None
    concept_catalog: tuple[Mapping[str, object], ...] = ()


def build_conversation_v5_turn_service(
    *,
    services: V5Services,
    focus: FocusedEntityReader,
    interpreter: InterpreterV5,
    receipts: CommandReceiptStore | None = None,
    audit: TurnAuditWriterV5 | None = None,
    clock: Clock | None = None,
) -> ConversationTurnV5:
    """Assemble the V5 turn module over the explicit services."""
    clock = clock or (lambda: datetime.now(timezone.utc))
    pending_reader = ProposalsPendingReaderV5(proposals=services.proposals)
    contexts = ContextAssemblerV5(
        chat=services.chat,
        radar=services.radar,
        preferences=services.preferences,
        pending=pending_reader,
        focus=focus,
        clock=clock,
    )
    executor = EffectExecutorV5(
        radar=services.radar,
        chat=services.chat,
        proposals=services.proposals,
        preferences=services.preferences,
        feedback=services.feedback,
        concepts=services.concepts,
        intensity_policy=services.intensity_policy,
    )
    return ConversationTurnV5(
        contexts=contexts,
        interpreter=interpreter,
        policy=plan_turn_v5,
        executor=executor,
        pending=ProposalsPendingResolverV5(proposals=services.proposals),
        receipts=receipts or InMemoryCommandReceiptStore(),
        audit=audit,
        clock=clock,
    )


def build_v5_graph(
    *,
    services: V5Services,
    focus: FocusedEntityReader,
    gateway: ModelGateway,
    interpretation_schema: Mapping[str, object],
    reply_schema: Mapping[str, object],
    model_version: str = "gpt-4.1-mini",
    prompt_version: str = "interpretation-v5",
    reply_prompt_version: str = "reply-v5",
    receipts: CommandReceiptStore | None = None,
    audit: TurnAuditWriterV5 | None = None,
    checkpointer: object | None = None,
    clock: Clock | None = None,
) -> object:
    """Compose the V5 graph over the explicit services."""
    interpreter = InterpretationCompilerV5(
        gateway=gateway,
        schema=interpretation_schema,
        prompt_version=prompt_version,
        model_version=model_version,
        concept_catalog=services.concept_catalog,
    )
    turn = build_conversation_v5_turn_service(
        services=services,
        focus=focus,
        interpreter=interpreter,
        receipts=receipts,
        audit=audit,
        clock=clock,
    )
    reply = ReplyComposerV5(
        gateway=gateway,
        schema=reply_schema,
        prompt_version=reply_prompt_version,
        model_version=model_version,
    )
    return build_graph_v5(
        dependencies=GraphDepsV5(turn=turn, reply=reply),
        checkpointer=checkpointer,
    )
