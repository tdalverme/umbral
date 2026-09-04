"""Productive V5 conversation scenarios over the real application seam."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from tests.fakes.preferences import FakeConceptReader, FakePreferenceStore
from tests.support.chat import (
    FixedProfileStatusReader,
    InMemoryChatMessageRepository,
    InMemoryChatSessionRepository,
    RecordingEventWriter,
)
from tests.support.radar import RadarTestContext

from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.chat.service import ChatService
from umbral.application.conversation.v5.contracts import (
    ConceptLinkV5,
    EvidenceSpan,
    ExpressDesire,
    ResolvePending,
    SetFilter,
    SetFilterCommand,
    TurnContextV5,
    TurnInterpretationV5,
)
from umbral.application.conversation.v5.ports import FocusedListingV5
from umbral.application.conversation.v5.receipts import InMemoryCommandReceiptStore
from umbral.application.conversation.v5.reply import ReplyComposerV5
from umbral.application.conversation.v5.service import ConversationTurnV5
from umbral.application.preferences.contracts import (
    PreferenceConcept,
    PreferencePolicySpec,
)
from umbral.application.preferences.intensity import load_intensity_policy
from umbral.application.preferences.service import PreferenceService
from umbral.infrastructure.conversation.v5.composition import (
    V5Services,
    build_conversation_v5_turn_service,
)
from umbral.infrastructure.conversation.v5.context import (
    ContextAssemblerV5,
    ProposalsPendingReaderV5,
)
from umbral.infrastructure.conversation.v5.executor import EffectExecutorV5
from umbral.infrastructure.playground.in_memory import LocalProposalRepository
from umbral.infrastructure.radar.contract_loader import load_events_registry

_NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
_ROOT = Path(__file__).resolve().parents[3]
_REPLY_SCHEMA = json.loads(
    (_ROOT / "contracts" / "agent" / "v5" / "reply-schema-v5.json").read_text(
        encoding="utf-8"
    )
)


class _ManagedReply:
    def generate_structured(self, **kwargs: object) -> ModelResult:
        return ModelResult(
            content={
                "contract_version": "5",
                "text": "Listo.",
                "outcomes": [],
                "verified_refs": [],
                "source": "managed",
            },
            model_version="test",
            status="success",
            latency_ms=1,
        )


class _Focus:
    def verified_focus(
        self, *, user_id: UUID, session_id: UUID
    ) -> FocusedListingV5 | None:
        return None


@dataclass
class _Script:
    outputs: tuple[TurnInterpretationV5, ...]
    index: int = 0

    def interpret(
        self, *, message_text: str, context: TurnContextV5, correlation_id: UUID
    ):
        output = self.outputs[min(self.index, len(self.outputs) - 1)]
        self.index += 1
        return output


@dataclass
class _Stack:
    radar: RadarTestContext
    chat: ChatService
    session_id: UUID
    profile_id: UUID
    proposals_repo: LocalProposalRepository
    proposals: SearchProfileUpdateProposals
    preferences_store: FakePreferenceStore


def _stack() -> tuple[UUID, _Stack]:
    radar = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    profile, _ = radar.service.create_profile(
        owner_id=user_id,
        name="Radar",
        zones=(),
        budget_max=None,
        budget_min=None,
        min_rooms=None,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    chat = ChatService(
        sessions=InMemoryChatSessionRepository(),
        messages=InMemoryChatMessageRepository(),
        profile_status=FixedProfileStatusReader(),
        events_out=RecordingEventWriter(),
        events_registry=load_events_registry(),
        clock=lambda: _NOW,
    )
    session = chat.create_session(
        user_id=user_id,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )
    events = RecordingEventWriter()
    proposals_repo = LocalProposalRepository()
    proposals = SearchProfileUpdateProposals(
        repository=proposals_repo,
        radar=radar.service,
        events=events,
        events_registry=load_events_registry(),
        clock=lambda: _NOW,
    )
    preferences_store = FakePreferenceStore()
    return user_id, _Stack(
        radar,
        chat,
        session.session_id,
        profile.profile_id,
        proposals_repo,
        proposals,
        preferences_store,
    )


def _turn(stack: _Stack, script: _Script) -> ConversationTurnV5:
    concepts = FakeConceptReader(
        {
            "luminosidad": PreferenceConcept(
                key="luminosidad", matcher_type="signal_score", computable=True
            )
        }
    )
    preferences = PreferenceService(
        expressions=stack.preferences_store,
        bindings=stack.preferences_store,
        mutations=stack.preferences_store,
        concepts=concepts,
        policy=PreferencePolicySpec.v1(),
        clock=lambda: _NOW,
    )
    return build_conversation_v5_turn_service(
        services=V5Services(
            chat=stack.chat,
            radar=stack.radar.service,
            proposals=stack.proposals,
            preferences=preferences,
            concepts=concepts,
            intensity_policy=load_intensity_policy(),
        ),
        focus=_Focus(),
        interpreter=script,
        receipts=InMemoryCommandReceiptStore(),
        clock=lambda: _NOW,
    )


def _link() -> ConceptLinkV5:
    span = EvidenceSpan(start=9, end=22, text="bien luminoso")
    return ConceptLinkV5(
        concept_ref="luminosidad",
        confidence=0.95,
        polarity="positive",
        intensity="medium",
        evidence_spans=(span,),
    )


def _mixed_interpretation() -> TurnInterpretationV5:
    desire_span = EvidenceSpan(start=9, end=22, text="bien luminoso")
    budget_span = EvidenceSpan(start=25, end=28, text="900")
    return TurnInterpretationV5(
        model_version="test",
        prompt_version="test",
        acts=(
            ExpressDesire(
                act_id="desire-light",
                confidence=0.95,
                evidence_spans=(desire_span,),
                raw_text="bien luminoso",
                subject_ref="luminosidad",
                concept_links=(_link(),),
            ),
            SetFilter(
                act_id="budget",
                confidence=0.95,
                evidence_spans=(budget_span,),
                filter_key="budget_max",
                value=900,
            ),
            SetFilter(
                act_id="rooms",
                confidence=0.95,
                evidence_spans=(budget_span,),
                filter_key="min_rooms",
                value=2,
            ),
        ),
    )


def _process(
    turn: ConversationTurnV5,
    *,
    user_id: UUID,
    session_id: UUID,
    message_id: UUID,
    text: str,
) -> object:
    return turn.process(
        user_id=user_id,
        session_id=session_id,
        message_id=message_id,
        message_text=text,
        correlation_id=uuid4(),
    )


def test_v5_mixed_soft_hard_then_approve_exposes_next_head() -> None:
    user_id, stack = _stack()
    approve_text = "aprobar"
    script = _Script(
        (
            _mixed_interpretation(),
            TurnInterpretationV5(
                model_version="test",
                prompt_version="test",
                acts=(
                    ResolvePending(
                        act_id="approve",
                        confidence=1,
                        evidence_spans=(EvidenceSpan(0, 7, approve_text),),
                        pending_ref="",
                        decision="approve",
                    ),
                ),
            ),
        )
    )
    turn = _turn(stack, script)
    first = _process(
        turn,
        user_id=user_id,
        session_id=stack.session_id,
        message_id=uuid4(),
        text="prefiero bien luminoso y 900",
    )
    assert [outcome.status for outcome in first.outcomes] == [
        "applied",
        "pending",
        "pending",
    ]
    assert len(stack.preferences_store.bindings) == 1
    queue = stack.proposals.pending_for_session(
        search_profile_id=stack.profile_id, session_id=stack.session_id
    )
    assert len(queue) == 2
    script.outputs = (
        TurnInterpretationV5(
            model_version="test",
            prompt_version="test",
            acts=(
                ResolvePending(
                    act_id="approve",
                    confidence=1,
                    evidence_spans=(EvidenceSpan(0, 7, approve_text),),
                    pending_ref=f"pending:{queue[0].proposal_id}",
                    decision="approve",
                ),
            ),
        ),
    )
    second = _process(
        turn,
        user_id=user_id,
        session_id=stack.session_id,
        message_id=uuid4(),
        text=approve_text,
    )
    assert second.outcomes[0].status == "applied"
    assert second.context.pending_action is not None
    assert (
        second.context.pending_action.pending_ref == f"pending:{queue[1].proposal_id}"
    )


def test_v5_turn_reply_keeps_effectful_turn_deterministic() -> None:
    user_id, stack = _stack()
    turn = _turn(stack, _Script((_mixed_interpretation(),)))

    result = _process(
        turn,
        user_id=user_id,
        session_id=stack.session_id,
        message_id=uuid4(),
        text="prefiero bien luminoso y 900",
    )
    reply = ReplyComposerV5(
        gateway=_ManagedReply(),
        schema=_REPLY_SCHEMA,
        prompt_version="reply-v5",
        model_version="test",
    ).compose(result)

    assert reply.source == "deterministic_fallback"
    assert "luminosidad" in reply.text.casefold()
    assert "1 de 2" in reply.text
    assert reply.text.count("?") == 1


def test_v5_reject_then_correct_active_head_preserves_lineage() -> None:
    user_id, stack = _stack()
    executor = EffectExecutorV5(
        radar=stack.radar.service, chat=stack.chat, proposals=stack.proposals
    )
    pending_reader = ProposalsPendingReaderV5(proposals=stack.proposals)
    context_reader = ContextAssemblerV5(
        chat=stack.chat,
        radar=stack.radar.service,
        preferences=None,
        pending=pending_reader,
        focus=_Focus(),
        clock=lambda: _NOW,
    )
    context = context_reader.load(
        user_id=user_id, session_id=stack.session_id, correlation_id=uuid4()
    )
    first = executor.execute(
        command=SetFilterCommand(
            act_id="budget",
            filter_key="budget_max",
            value=900,
            expected_profile_version=1,
        ),
        context=context,
        idempotency_key="proposal:first",
    )
    assert first.status == "pending"
    second = executor.execute(
        command=SetFilterCommand(
            act_id="rooms", filter_key="min_rooms", value=2, expected_profile_version=1
        ),
        context=context,
        idempotency_key="proposal:second",
    )
    first_id = UUID(first.object_ref.removeprefix("proposal:"))
    second_id = UUID(second.object_ref.removeprefix("proposal:"))
    rejected = stack.proposals.reject(
        user_id=user_id,
        session_id=stack.session_id,
        search_profile_id=stack.profile_id,
        proposal_id=first_id,
        note="cambiar",
        correlation_id=uuid4(),
    )
    assert rejected.state == "rejected"
    assert rejected.rejection_reason == "user"
    current = stack.proposals.pending_for_session(
        search_profile_id=stack.profile_id, session_id=stack.session_id
    )
    assert len(current) == 1 and current[0].proposal_id == second_id
    correction_context = context_reader.load(
        user_id=user_id, session_id=stack.session_id, correlation_id=uuid4()
    )
    corrected = executor.execute(
        command=SetFilterCommand(
            act_id="rooms-correction",
            filter_key="min_rooms",
            value=3,
            expected_profile_version=1,
        ),
        context=correction_context,
        idempotency_key="proposal:correction",
    )
    corrected_id = UUID(corrected.object_ref.removeprefix("proposal:"))
    assert stack.proposals_repo.proposals[first_id].rejection_reason == "user"
    assert stack.proposals_repo.proposals[second_id].rejection_reason == "edited"
    assert (
        stack.proposals_repo.proposals[second_id].superseded_by_proposal_id
        == corrected_id
    )
    assert stack.proposals_repo.proposals[corrected_id].state == "pending"


def test_v5_receipt_replay_does_not_duplicate_hard_proposal() -> None:
    user_id, stack = _stack()
    text = "presupuesto 900"
    interpretation = TurnInterpretationV5(
        model_version="test",
        prompt_version="test",
        acts=(
            SetFilter(
                act_id="budget",
                confidence=1,
                evidence_spans=(EvidenceSpan(12, 15, "900"),),
                filter_key="budget_max",
                value=900,
            ),
        ),
    )
    turn = _turn(stack, _Script((interpretation, interpretation)))
    message_id = uuid4()
    first = _process(
        turn,
        user_id=user_id,
        session_id=stack.session_id,
        message_id=message_id,
        text=text,
    )
    second = _process(
        turn,
        user_id=user_id,
        session_id=stack.session_id,
        message_id=message_id,
        text=text,
    )
    assert first.outcomes[0].status == "pending"
    assert second.outcomes[0].status == "pending"
    assert len(stack.proposals_repo.proposals) == 1
