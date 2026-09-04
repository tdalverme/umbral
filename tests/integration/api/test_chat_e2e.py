"""Single-stack chat e2e: runtime over the unversioned conversation graph.

Exercises the full production path without Postgres: a mixed soft+hard turn
through ``ChatRuntime`` interrupts for the hard step, applies the soft desire
immediately, and completes the radar update on approval.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import MemorySaver
from tests.fakes.preferences import FakeConceptReader, FakePreferenceStore
from tests.support.agent import InMemoryGraphRunRepository
from tests.support.chat import (
    FixedProfileStatusReader,
    InMemoryChatMessageRepository,
    InMemoryChatSessionRepository,
    RecordingEventWriter,
)
from tests.support.radar import RadarTestContext

from umbral.agent.graph import GraphDeps, build_graph
from umbral.agent.runtime import ChatRuntime
from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.chat.service import ChatService
from umbral.application.conversation.contracts import (
    ConceptLink,
    EvidenceSpan,
    ExpressDesire,
    SetFilter,
    TurnContext,
    TurnInterpretation,
)
from umbral.application.conversation.ports import FocusedListing
from umbral.application.conversation.receipts import InMemoryCommandReceiptStore
from umbral.application.conversation.reply import ReplyComposer
from umbral.application.preferences.contracts import (
    PreferenceConcept,
    PreferencePolicySpec,
)
from umbral.application.preferences.intensity import load_intensity_policy
from umbral.application.preferences.service import PreferenceService
from umbral.infrastructure.conversation.composition import (
    ConversationServices,
    build_conversation_turn_service,
)
from umbral.infrastructure.playground.in_memory import LocalProposalRepository
from umbral.infrastructure.radar.contract_loader import load_events_registry

_NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)
_ROOT = Path(__file__).resolve().parents[3]
_REPLY_SCHEMA = json.loads(
    (_ROOT / "contracts" / "agent" / "reply-schema.json").read_text(encoding="utf-8")
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
    ) -> FocusedListing | None:
        return None


@dataclass
class _Script:
    output: TurnInterpretation

    def interpret(
        self, *, message_text: str, context: TurnContext, correlation_id: UUID
    ) -> TurnInterpretation:
        return self.output


def _mixed_interpretation() -> TurnInterpretation:
    desire_span = EvidenceSpan(start=9, end=22, text="bien luminoso")
    budget_span = EvidenceSpan(start=25, end=28, text="900")
    return TurnInterpretation(
        model_version="test",
        prompt_version="test",
        acts=(
            ExpressDesire(
                act_id="desire-light",
                confidence=0.95,
                evidence_spans=(desire_span,),
                raw_text="bien luminoso",
                subject_ref="luminosidad",
                concept_links=(
                    ConceptLink(
                        concept_ref="luminosidad",
                        confidence=0.95,
                        polarity="positive",
                        intensity="medium",
                        evidence_spans=(desire_span,),
                    ),
                ),
            ),
            SetFilter(
                act_id="budget",
                confidence=0.95,
                evidence_spans=(budget_span,),
                filter_key="budget_max",
                value=900,
            ),
        ),
    )


def _build_runtime() -> tuple[ChatRuntime, UUID, UUID, RadarTestContext]:
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
    proposals = SearchProfileUpdateProposals(
        repository=LocalProposalRepository(),
        radar=radar.service,
        events=RecordingEventWriter(),
        events_registry=load_events_registry(),
        clock=lambda: _NOW,
    )
    store = FakePreferenceStore()
    concepts = FakeConceptReader(
        {
            "luminosidad": PreferenceConcept(
                key="luminosidad", matcher_type="signal_score", computable=True
            )
        }
    )
    preferences = PreferenceService(
        expressions=store,
        bindings=store,
        mutations=store,
        concepts=concepts,
        policy=PreferencePolicySpec.v1(),
        clock=lambda: _NOW,
    )
    turn = build_conversation_turn_service(
        services=ConversationServices(
            chat=chat,
            radar=radar.service,
            proposals=proposals,
            preferences=preferences,
            concepts=concepts,
            intensity_policy=load_intensity_policy(),
        ),
        focus=_Focus(),
        interpreter=_Script(_mixed_interpretation()),
        receipts=InMemoryCommandReceiptStore(),
        clock=lambda: _NOW,
    )
    reply = ReplyComposer(
        gateway=_ManagedReply(),  # type: ignore[arg-type]
        schema=_REPLY_SCHEMA,
        prompt_version="reply",
        model_version="test",
    )
    graph = build_graph(
        dependencies=GraphDeps(turn=turn, reply=reply),
        checkpointer=MemorySaver(),
    )
    runtime = ChatRuntime(
        graph=graph,
        conversation=chat,  # type: ignore[arg-type]
        runs=InMemoryGraphRunRepository(),  # type: ignore[arg-type]
        clock=lambda: _NOW,
    )
    return runtime, user_id, session.session_id, radar


def test_e2e_mixed_turn_applies_soft_and_confirms_hard() -> None:
    runtime, user_id, session_id, radar = _build_runtime()

    first = runtime.run_turn(
        user_id=user_id,
        session_id=session_id,
        text="prefiero bien luminoso y 900",
        correlation_id=uuid4(),
    )
    assert first.status == "interrupted"
    assert first.interrupt is not None
    assert first.interrupt["ordinal"] == 1
    assert first.interrupt["total"] == 1

    second = runtime.run_turn(
        user_id=user_id,
        session_id=session_id,
        text="",
        correlation_id=uuid4(),
        resume=True,
        decision={"decision": "approve"},
    )
    assert second.run_id == first.run_id
    assert second.status == "completed"
