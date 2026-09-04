"""Unit tests for V5 desire command execution."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from tests.fakes.preferences import FakeConceptReader
from tests.support.radar import RadarTestContext

from umbral.application.conversation.contracts import (
    ConceptLink,
    RecordDesireCommand,
    ReviseDesireCommand,
    TurnContext,
    WithdrawDesireCommand,
)
from umbral.application.preferences.contracts import (
    BindingDraft,
    PreferenceAuthority,
    PreferenceChange,
    PreferenceConcept,
    PreferenceExpression,
    PreferenceView,
)
from umbral.application.preferences.intensity import load_intensity_policy
from umbral.infrastructure.conversation.executor import EffectExecutor

_NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)


class _FakePreferences:
    def __init__(self) -> None:
        self.recorded: SimpleNamespace | None = None
        self.revised: SimpleNamespace | None = None
        self.withdrawn: SimpleNamespace | None = None

    def record_expression(
        self,
        *,
        profile_id: UUID,
        source_message_id: UUID | None,
        subject_key: str,
        raw_text: str,
        authority: PreferenceAuthority,
        binding_drafts: tuple[BindingDraft, ...],
        correlation_id: UUID,
    ) -> PreferenceChange:
        self.recorded = SimpleNamespace(
            profile_id=profile_id,
            subject_key=subject_key,
            raw_text=raw_text,
            authority=authority,
            binding_drafts=binding_drafts,
        )
        return _change(subject_key, raw_text)

    def revise_expression(
        self,
        *,
        profile_id: UUID,
        previous_expression_id: UUID,
        source_message_id: UUID | None,
        raw_text: str,
        authority: PreferenceAuthority,
        binding_drafts: tuple[BindingDraft, ...],
        correlation_id: UUID,
    ) -> PreferenceChange:
        self.revised = SimpleNamespace(
            profile_id=profile_id,
            previous_expression_id=previous_expression_id,
            raw_text=raw_text,
            authority=authority,
            binding_drafts=binding_drafts,
        )
        return _change("balcon", raw_text)

    def set_explicit_preference(
        self,
        *,
        profile_id: UUID,
        source_message_id: UUID | None,
        concept_key: str,
        raw_text: str,
        binding_draft: BindingDraft,
        correlation_id: UUID,
    ) -> PreferenceChange:
        self.recorded = SimpleNamespace(
            profile_id=profile_id,
            subject_key=concept_key,
            raw_text=raw_text,
            authority="explicit",
            binding_drafts=(binding_draft,),
        )
        return _change(concept_key, raw_text)

    def withdraw_expression(
        self,
        *,
        profile_id: UUID,
        expression_id: UUID,
        correlation_id: UUID,
    ) -> PreferenceChange:
        self.withdrawn = SimpleNamespace(
            profile_id=profile_id, expression_id=expression_id
        )
        return _change("balcon", "Ya no quiero balcón")

    def active_view(self, profile_id: UUID) -> tuple[PreferenceView, ...]:
        return ()


def _change(subject_key: str, raw_text: str) -> PreferenceChange:
    return PreferenceChange(
        expression=PreferenceExpression(
            expression_id=uuid4(),
            profile_id=uuid4(),
            source_message_id=None,
            source_kind="chat",
            subject_key=subject_key,
            raw_text=raw_text,
            authority="explicit",
            status="active",
            superseded_by=None,
            original_text_available=True,
            created_at=_NOW,
            correlation_id=uuid4(),
        ),
        bindings=(),
        fact_ids=(),
    )


def _context(*, profile_id: UUID, user_id: UUID, session_id: UUID) -> TurnContext:
    return TurnContext(
        user_id=str(user_id),
        session_id=str(session_id),
        active_radar_ref=f"radar:{profile_id}",
        active_radar_version=1,
        current_filters=(),
        active_desires=(),
        pending_action=None,
        focused_entity=None,
        verified_listing_refs=(),
        allowed_capabilities=(
            "express_desire",
            "revise_desire",
            "withdraw_desire",
            "query",
        ),
        untrusted_content=(),
        context_schema_version="5",
        correlation_id=str(uuid4()),
    )


def _executor(radar_ctx: RadarTestContext) -> tuple[EffectExecutor, _FakePreferences]:
    preferences = _FakePreferences()
    executor = EffectExecutor(
        radar=radar_ctx.service,
        chat=None,  # type: ignore[arg-type]
        proposals=None,  # type: ignore[arg-type]
        preferences=preferences,
        concepts=FakeConceptReader(
            {
                "movilidad_cotidiana": PreferenceConcept(
                    key="movilidad_cotidiana",
                    matcher_type="numeric_range",
                    computable=True,
                )
            }
        ),
        intensity_policy=load_intensity_policy(),
    )
    return executor, preferences


def test_out_of_catalog_desire_is_persisted_with_zero_concept_links() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    profile, _ = radar_ctx.service.create_profile(
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
    executor, preferences = _executor(radar_ctx)
    context = _context(
        profile_id=profile.profile_id, user_id=user_id, session_id=uuid4()
    )

    result = executor.execute(
        command=RecordDesireCommand(
            act_id="a1",
            raw_text="Quiero algo moderno",
            subject_ref="moderno",
            concept_links=(),
        ),
        context=context,
        idempotency_key="turn:a0",
    )

    assert result.status == "applied"
    assert result.effect_key == "desire.remembered"
    assert preferences.recorded is not None
    assert preferences.recorded.binding_drafts == (
        BindingDraft.unresolved("no_structured_evidence"),
    )
    assert preferences.recorded.subject_key == "moderno"
    assert preferences.recorded.raw_text == "Quiero algo moderno"


def test_revise_desire_uses_authorized_expression_ref() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    profile, _ = radar_ctx.service.create_profile(
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
    executor, preferences = _executor(radar_ctx)
    context = _context(
        profile_id=profile.profile_id, user_id=user_id, session_id=uuid4()
    )
    expression_id = uuid4()

    result = executor.execute(
        command=ReviseDesireCommand(
            act_id="a1",
            desire_ref=f"desire:{expression_id}",
            raw_text="Ahora prefiero con balcón",
            concept_links=(),
        ),
        context=context,
        idempotency_key="turn:a0",
    )

    assert result.status == "applied"
    assert result.effect_key == "desire.revised"
    assert preferences.revised is not None
    assert preferences.revised.previous_expression_id == expression_id
    assert preferences.revised.raw_text == "Ahora prefiero con balcón"


def test_declared_registry_concept_uses_its_matcher_without_an_executor_allowlist(
) -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    profile, _ = radar_ctx.service.create_profile(
        owner_id=user_id, name="Radar", zones=(), budget_max=None, budget_min=None,
        min_rooms=None, surface_min=None, surface_max=None, unknown_strategy=None,
        correlation_id=uuid4(),
    )
    executor, preferences = _executor(radar_ctx)

    result = executor.execute(
        command=RecordDesireCommand(
            act_id="a1", raw_text="Quiero moverme fácil", subject_ref="alias libre",
            concept_links=(
                ConceptLink(
                    concept_ref="movilidad_cotidiana", confidence=0.9,
                    polarity="positive", intensity="high",
                ),
            ),
        ),
        context=_context(
            profile_id=profile.profile_id, user_id=user_id, session_id=uuid4()
        ),
        idempotency_key="turn:a0",
    )

    assert result.status == "applied"
    assert preferences.recorded is not None
    binding = preferences.recorded.binding_drafts[0]
    assert binding.concept_key == "movilidad_cotidiana"
    assert binding.matcher_type == "numeric_range"
    assert binding.params["weight"] == 0.75


def test_invented_concept_ref_is_rejected_without_a_lexical_fallback() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    profile, _ = radar_ctx.service.create_profile(
        owner_id=user_id, name="Radar", zones=(), budget_max=None, budget_min=None,
        min_rooms=None, surface_min=None, surface_max=None, unknown_strategy=None,
        correlation_id=uuid4(),
    )
    executor, preferences = _executor(radar_ctx)

    result = executor.execute(
        command=RecordDesireCommand(
            act_id="a1", raw_text="Quiero teletransporte", subject_ref="teletransporte",
            concept_links=(
                ConceptLink(
                    concept_ref="teletransporte", confidence=0.9,
                    polarity="positive", intensity="medium",
                ),
            ),
        ),
        context=_context(
            profile_id=profile.profile_id, user_id=user_id, session_id=uuid4()
        ),
        idempotency_key="turn:a0",
    )

    assert result.status == "rejected"
    assert result.reason_code == "preferences.structured_concept_not_found"
    assert preferences.recorded is None


def test_withdraw_desire_uses_authorized_expression_ref() -> None:
    radar_ctx = RadarTestContext(default_runtime=False)
    user_id = uuid4()
    profile, _ = radar_ctx.service.create_profile(
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
    executor, preferences = _executor(radar_ctx)
    context = _context(
        profile_id=profile.profile_id, user_id=user_id, session_id=uuid4()
    )
    expression_id = uuid4()

    result = executor.execute(
        command=WithdrawDesireCommand(
            act_id="a1", desire_ref=f"desire:{expression_id}"
        ),
        context=context,
        idempotency_key="turn:a0",
    )

    assert result.status == "applied"
    assert result.effect_key == "desire.withdrawn"
    assert preferences.withdrawn is not None
    assert preferences.withdrawn.expression_id == expression_id
