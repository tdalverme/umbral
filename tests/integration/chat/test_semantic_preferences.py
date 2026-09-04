"""Regression seam for scripted semantic preferences over the V5 turn path."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import pytest
from tests.fakes.preferences import FakeConceptReader, FakePreferenceStore

from umbral.application.conversation.v5.contracts import (
    ConceptLinkV5,
    ConversationTurnResultV5,
    EvidenceSpan,
    ExpressDesire,
    TurnContextV5,
    TurnInterpretationV5,
)
from umbral.application.conversation.v5.policy import plan_turn_v5
from umbral.application.conversation.v5.receipts import InMemoryCommandReceiptStore
from umbral.application.conversation.v5.service import ConversationTurnV5
from umbral.application.preferences.contracts import (
    PreferenceConcept,
    PreferencePolicySpec,
)
from umbral.application.preferences.intensity import load_intensity_policy
from umbral.application.preferences.service import PreferenceService
from umbral.infrastructure.conversation.v5.executor import EffectExecutorV5

USER_ID = UUID(int=1)
SESSION_ID = UUID(int=2)
MESSAGE_ID = UUID(int=3)
CORRELATION_ID = UUID(int=4)
PROFILE_ID = UUID(int=5)


@dataclass
class ScriptedSemanticGateway:
    """Returns supplied semantic output without inspecting the user message."""

    output: TurnInterpretationV5
    calls: int = 0

    def interpret(
        self,
        *,
        message_text: str,
        context: TurnContextV5,
        correlation_id: UUID,
    ) -> TurnInterpretationV5:
        self.calls += 1
        return self.output


@dataclass(frozen=True)
class _ContextReader:
    context: TurnContextV5

    def load(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        correlation_id: UUID,
    ) -> TurnContextV5:
        return self.context


class _NoopPendingResolver:
    def resolve(self, **_: object) -> object:
        raise AssertionError("semantic preferences must not require confirmation")


@dataclass(frozen=True)
class SemanticScenario:
    message: str
    output: TurnInterpretationV5
    concept_keys: tuple[str, ...]


def _context() -> TurnContextV5:
    return TurnContextV5(
        user_id=str(USER_ID),
        session_id=str(SESSION_ID),
        active_radar_ref=f"radar:{PROFILE_ID}",
        active_radar_version=1,
        current_filters=(),
        active_desires=(),
        pending_action=None,
        focused_entity=None,
        verified_listing_refs=(),
        allowed_capabilities=("express_desire",),
        untrusted_content=(),
        context_schema_version="5",
        correlation_id=str(CORRELATION_ID),
    )


def _output(*acts: ExpressDesire) -> TurnInterpretationV5:
    return TurnInterpretationV5(
        model_version="semantic-gateway-scripted",
        prompt_version="semantic-preferences-regression",
        acts=acts,
    )


def _desire(
    *,
    act_id: str,
    raw_text: str,
    concept_key: str,
    evidence: EvidenceSpan,
) -> ExpressDesire:
    return ExpressDesire(
        act_id=act_id,
        confidence=0.90,
        evidence_spans=(evidence,),
        raw_text=raw_text,
        subject_ref=concept_key,
        concept_links=(
            ConceptLinkV5(
                concept_ref=concept_key,
                confidence=0.90,
                polarity="positive",
                intensity="medium",
                evidence_spans=(evidence,),
            ),
        ),
    )


_SCENARIOS = (
    SemanticScenario(
        message="prefiero deptos con buen acceso al transporte",
        output=_output(
            _desire(
                act_id="transport",
                raw_text="buen acceso al transporte",
                concept_key="acceso_transporte",
                evidence=EvidenceSpan(
                    start=20, end=45, text="buen acceso al transporte"
                ),
            )
        ),
        concept_keys=("acceso_transporte",),
    ),
    SemanticScenario(
        message="quiero deptos con cafés cerca",
        output=_output(
            _desire(
                act_id="cafes",
                raw_text="cafés cerca",
                concept_key="proximidad_cafes",
                evidence=EvidenceSpan(start=18, end=29, text="cafés cerca"),
            )
        ),
        concept_keys=("proximidad_cafes",),
    ),
    SemanticScenario(
        message=(
            "Me gustan deptos luminosos y silenciosos. "
            "Si está bien conectado, mejor"
        ),
        output=_output(
            _desire(
                act_id="light",
                raw_text="luminosos",
                concept_key="luminosidad",
                evidence=EvidenceSpan(start=17, end=26, text="luminosos"),
            ),
            _desire(
                act_id="quiet",
                raw_text="silenciosos",
                concept_key="calma_residencial",
                evidence=EvidenceSpan(start=29, end=40, text="silenciosos"),
            ),
            _desire(
                act_id="transport",
                raw_text="bien conectado",
                concept_key="acceso_transporte",
                evidence=EvidenceSpan(start=50, end=64, text="bien conectado"),
            ),
        ),
        concept_keys=("luminosidad", "calma_residencial", "acceso_transporte"),
    ),
    SemanticScenario(
        message="Me encanta que entre el sol a la tarde",
        output=_output(
            _desire(
                act_id="sun",
                raw_text="entre el sol a la tarde",
                concept_key="luminosidad",
                evidence=EvidenceSpan(
                    start=15, end=38, text="entre el sol a la tarde"
                ),
            )
        ),
        concept_keys=("luminosidad",),
    ),
    SemanticScenario(
        message="Necesito descansar lejos del estruendo",
        output=_output(
            _desire(
                act_id="quiet",
                raw_text="lejos del estruendo",
                concept_key="calma_residencial",
                evidence=EvidenceSpan(
                    start=19, end=38, text="lejos del estruendo"
                ),
            )
        ),
        concept_keys=("calma_residencial",),
    ),
    SemanticScenario(
        message="Quiero llegar al subte caminando en minutos",
        output=_output(
            _desire(
                act_id="subway",
                raw_text="llegar al subte caminando",
                concept_key="acceso_transporte",
                evidence=EvidenceSpan(
                    start=7, end=32, text="llegar al subte caminando"
                ),
            )
        ),
        concept_keys=("acceso_transporte",),
    ),
    SemanticScenario(
        message="Busco verde a pocas cuadras",
        output=_output(
            _desire(
                act_id="green",
                raw_text="verde a pocas cuadras",
                concept_key="proximidad_parque",
                evidence=EvidenceSpan(
                    start=6, end=27, text="verde a pocas cuadras"
                ),
            )
        ),
        concept_keys=("proximidad_parque",),
    ),
)


def _preference_service(store: FakePreferenceStore) -> PreferenceService:
    return PreferenceService(
        expressions=store,
        bindings=store,
        mutations=store,
        concepts=FakeConceptReader(
            {
                "acceso_transporte": PreferenceConcept(
                    key="acceso_transporte",
                    matcher_type="signal_score",
                    computable=True,
                ),
                "proximidad_cafes": PreferenceConcept(
                    key="proximidad_cafes",
                    matcher_type="signal_score",
                    computable=True,
                ),
                "luminosidad": PreferenceConcept(
                    key="luminosidad",
                    matcher_type="semantic_feature",
                    computable=True,
                ),
                "calma_residencial": PreferenceConcept(
                    key="calma_residencial",
                    matcher_type="signal_score",
                    computable=True,
                ),
                "proximidad_parque": PreferenceConcept(
                    key="proximidad_parque",
                    matcher_type="signal_score",
                    computable=True,
                ),
            }
        ),
        policy=PreferencePolicySpec.v1(),
        clock=lambda: datetime(2026, 9, 3, tzinfo=timezone.utc),
    )


def _process(
    scenario: SemanticScenario,
) -> tuple[ConversationTurnResultV5, ScriptedSemanticGateway, FakePreferenceStore]:
    store = FakePreferenceStore()
    gateway = ScriptedSemanticGateway(scenario.output)
    preferences = _preference_service(store)
    turn = ConversationTurnV5(
        contexts=_ContextReader(_context()),
        interpreter=gateway,
        policy=plan_turn_v5,
        executor=EffectExecutorV5(
            radar=None,  # type: ignore[arg-type]
            chat=None,  # type: ignore[arg-type]
            proposals=None,  # type: ignore[arg-type]
            preferences=preferences,
            concepts=preferences.concepts,
            intensity_policy=load_intensity_policy(),
        ),
        pending=_NoopPendingResolver(),  # type: ignore[arg-type]
        receipts=InMemoryCommandReceiptStore(),
    )
    result = turn.process(
        user_id=USER_ID,
        session_id=SESSION_ID,
        message_id=MESSAGE_ID,
        message_text=scenario.message,
        correlation_id=CORRELATION_ID,
    )
    return result, gateway, store


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=lambda item: item.message)
def test_scripted_semantic_preferences_persist_as_medium_soft_bindings(
    scenario: SemanticScenario,
) -> None:
    """Exact user wording reaches durable semantic bindings without HITL."""
    result, gateway, store = _process(scenario)

    assert gateway.calls == 1
    assert result.failure_stage is None
    assert [outcome.status for outcome in result.outcomes] == [
        "applied"
    ] * len(scenario.concept_keys)
    assert [binding.concept_key for binding in store.bindings] == list(
        scenario.concept_keys
    )
    assert [binding.mode for binding in store.bindings] == ["soft"] * len(
        scenario.concept_keys
    )
    assert [binding.params.get("weight") for binding in store.bindings] == [
        0.50
    ] * len(scenario.concept_keys)
    assert [binding.params.get("polarity") for binding in store.bindings] == [
        "positive"
    ] * len(scenario.concept_keys)
    assert [binding.params.get("intensity") for binding in store.bindings] == [
        "medium"
    ] * len(scenario.concept_keys)
    assert [
        binding.params.get("intensity_policy_version") for binding in store.bindings
    ] == [
        "preference-intensity-v1"
    ] * len(scenario.concept_keys)
    assert all(binding.evidence_refs for binding in store.bindings)
    assert len({repr(binding.evidence_refs) for binding in store.bindings}) == len(
        scenario.concept_keys
    )
