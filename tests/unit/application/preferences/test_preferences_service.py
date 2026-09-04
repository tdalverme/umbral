"""PreferenceService keeps expressed intent separate from computable facts."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from tests.fakes.preferences import (
    FakeConceptReader,
    FakePreferenceStore,
)

from umbral.application.preferences.contracts import (
    BindingDraft,
    PreferenceAuthorityError,
    PreferenceConcept,
    PreferencePolicySpec,
    PreferenceValidationError,
)
from umbral.application.preferences.service import PreferenceService


@pytest.fixture
def preference_service() -> PreferenceService:
    store = FakePreferenceStore()
    return PreferenceService(
        expressions=store,
        bindings=store,
        mutations=store,
        concepts=FakeConceptReader(
            {
                "balcon": PreferenceConcept(
                    key="balcon", matcher_type="categorical", computable=True
                ),
                "calma_residencial": PreferenceConcept(
                    key="calma_residencial",
                    matcher_type="signal_score",
                    computable=True,
                ),
            }
        ),
        policy=PreferencePolicySpec.v1(),
        clock=lambda: datetime(2026, 8, 14, tzinfo=timezone.utc),
    )


def test_unknown_desire_is_preserved_without_fact(
    preference_service: PreferenceService,
) -> None:
    change = preference_service.record_expression(
        profile_id=uuid4(),
        source_message_id=uuid4(),
        subject_key="cocina_grande",
        raw_text="quiero una cocina grande",
        authority="explicit",
        binding_drafts=(BindingDraft.unresolved("no_reliable_evidence"),),
        correlation_id=uuid4(),
    )

    assert change.expression.raw_text == "quiero una cocina grande"
    assert change.bindings[0].kind == "unresolved"
    assert change.fact_ids == ()


def test_passive_signal_cannot_supersede_explicit_expression(
    preference_service: PreferenceService,
) -> None:
    profile_id = uuid4()
    explicit = preference_service.record_expression(
        profile_id=profile_id,
        source_message_id=uuid4(),
        subject_key="balcon",
        raw_text="quiero balcon",
        authority="explicit",
        binding_drafts=(BindingDraft.unresolved("not_measurable"),),
        correlation_id=uuid4(),
    ).expression

    with pytest.raises(PreferenceAuthorityError):
        preference_service.revise_expression(
            profile_id=profile_id,
            previous_expression_id=explicit.expression_id,
            source_message_id=None,
            raw_text="parece que no quiere balcon",
            authority="passive",
            binding_drafts=(BindingDraft.unresolved("passive_only"),),
            correlation_id=uuid4(),
        )


def test_revision_supersedes_prior_expression_with_lineage(
    preference_service: PreferenceService,
) -> None:
    profile_id = uuid4()
    original = preference_service.record_expression(
        profile_id=profile_id,
        source_message_id=uuid4(),
        subject_key="balcon",
        raw_text="quiero balcon",
        authority="explicit",
        binding_drafts=(BindingDraft.unresolved("not_measurable"),),
        correlation_id=uuid4(),
    ).expression

    revised = preference_service.revise_expression(
        profile_id=profile_id,
        previous_expression_id=original.expression_id,
        source_message_id=uuid4(),
        raw_text="no quiero balcon",
        authority="explicit",
        binding_drafts=(BindingDraft.unresolved("not_measurable"),),
        correlation_id=uuid4(),
    )

    retired = preference_service.expressions.get(original.expression_id)
    assert retired is not None
    assert retired.status == "superseded"
    assert retired.superseded_by == revised.expression.expression_id
    assert [item.raw_text for item in preference_service.active_view(profile_id)] == [
        "no quiero balcon"
    ]


def test_only_computable_structured_binding_produces_a_fact(
    preference_service: PreferenceService,
) -> None:
    change = preference_service.record_expression(
        profile_id=uuid4(),
        source_message_id=uuid4(),
        subject_key="balcon",
        raw_text="quiero balcon",
        authority="explicit",
        binding_drafts=(
            BindingDraft.structured(
                concept_key="balcon",
                matcher_type="categorical",
                params={"preferred_value": True},
                confidence=0.9,
            ),
            BindingDraft.semantic(
                query_embedding=(0.1, 0.2),
                embedding_version_id=uuid4(),
                confidence=0.5,
            ),
        ),
        correlation_id=uuid4(),
    )

    assert len(change.fact_ids) == 1
    assert [binding.kind for binding in change.bindings] == ["structured", "semantic"]


def test_hard_structured_binding_requires_a_recorded_confirmation(
    preference_service: PreferenceService,
) -> None:
    with pytest.raises(PreferenceValidationError) as raised:
        preference_service.record_expression(
            profile_id=uuid4(),
            source_message_id=uuid4(),
            subject_key="balcon",
            raw_text="solo con balcon",
            authority="explicit",
            binding_drafts=(
                BindingDraft.structured(
                    concept_key="balcon",
                    matcher_type="categorical",
                    params={"preferred_value": True},
                    confidence=0.9,
                    mode="hard",
                ),
            ),
            correlation_id=uuid4(),
        )

    assert raised.value.error_codes == (
        "preferences.hard_binding_requires_confirmation",
    )


def test_withdrawal_keeps_expression_lineage_and_removes_active_bindings(
    preference_service: PreferenceService,
) -> None:
    profile_id = uuid4()
    created = preference_service.record_expression(
        profile_id=profile_id,
        source_message_id=uuid4(),
        subject_key="cocina_grande",
        raw_text="quiero una cocina grande",
        authority="explicit",
        binding_drafts=(BindingDraft.unresolved("no_evidence"),),
        correlation_id=uuid4(),
    )

    withdrawn = preference_service.withdraw_expression(
        profile_id=profile_id,
        expression_id=created.expression.expression_id,
        correlation_id=uuid4(),
    )

    assert withdrawn.expression.status == "withdrawn"
    assert withdrawn.bindings[0].status == "superseded"
    assert preference_service.active_view(profile_id) == ()


def test_active_view_exposes_interpretation_but_not_query_embedding(
    preference_service: PreferenceService,
) -> None:
    profile_id = uuid4()
    preference_service.record_expression(
        profile_id=profile_id,
        source_message_id=uuid4(),
        subject_key="cerca_parque",
        raw_text="quiero estar cerca de un parque",
        authority="explicit",
        binding_drafts=(
            BindingDraft.semantic(
                query_embedding=(0.1, 0.2),
                embedding_version_id=uuid4(),
                confidence=0.6,
            ),
        ),
        correlation_id=uuid4(),
    )

    view = preference_service.active_view(profile_id)

    assert view[0].raw_text == "quiero estar cerca de un parque"
    assert view[0].binding_kind == "semantic"
    assert not hasattr(view[0], "query_embedding")


def test_explicit_preference_replaces_the_active_fact_for_its_canonical_concept(
    preference_service: PreferenceService,
) -> None:
    """A repeated concept must supersede, rather than accumulate, its fact."""
    profile_id = uuid4()
    first = preference_service.set_explicit_preference(
        profile_id=profile_id,
        source_message_id=uuid4(),
        concept_key="calma_residencial",
        raw_text="Busco poco ruido",
        binding_draft=BindingDraft.structured(
            concept_key="calma_residencial",
            matcher_type="signal_score",
            params={
                "polarity": "positive",
                "intensity": "low",
                "weight": 0.25,
                "intensity_policy_version": "preference-intensity-v1",
            },
            confidence=0.9,
        ),
        correlation_id=uuid4(),
    )

    replacement = preference_service.set_explicit_preference(
        profile_id=profile_id,
        source_message_id=uuid4(),
        concept_key="calma_residencial",
        raw_text="Es esencial que sea silencioso",
        binding_draft=BindingDraft.structured(
            concept_key="calma_residencial",
            matcher_type="signal_score",
            params={
                "polarity": "positive",
                "intensity": "essential",
                "weight": 1.0,
                "intensity_policy_version": "preference-intensity-v1",
            },
            confidence=0.9,
        ),
        correlation_id=uuid4(),
    )

    retired = preference_service.expressions.get(first.expression.expression_id)
    assert retired is not None
    assert retired.status == "superseded"
    assert retired.superseded_by == replacement.expression.expression_id
    assert [
        view.concept_key for view in preference_service.active_view(profile_id)
    ] == [
        "calma_residencial"
    ]
    assert preference_service.active_view(profile_id)[0].intensity == "essential"
    assert preference_service.active_view(profile_id)[0].weight == 1.0


def test_explicit_preference_replaces_polarity_for_the_same_canonical_concept(
    preference_service: PreferenceService,
) -> None:
    profile_id = uuid4()
    for polarity in ("positive", "negative"):
        preference_service.set_explicit_preference(
            profile_id=profile_id,
            source_message_id=uuid4(),
            concept_key="calma_residencial",
            raw_text=f"{polarity} calma",
            binding_draft=BindingDraft.structured(
                concept_key="calma_residencial",
                matcher_type="signal_score",
                params={
                    "polarity": polarity,
                    "intensity": "high",
                    "weight": 0.75,
                    "intensity_policy_version": "preference-intensity-v1",
                },
                confidence=0.9,
            ),
            correlation_id=uuid4(),
        )

    views = preference_service.active_view(profile_id)
    assert len(views) == 1
    assert views[0].polarity == "negative"
