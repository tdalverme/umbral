"""Real PostgreSQL conformance tests for the preference persistence seam."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from tests.integration.preferences.conftest import PreferenceStack

from umbral.application.preferences.contracts import BindingDraft
from umbral.infrastructure.db.models.criteria import PreferenceFact
from umbral.infrastructure.db.models.preferences import (
    CriterionBinding,
    PreferenceExpression,
)


def test_repository_persists_multiple_bindings_and_fact_lineage(
    preference_stack: PreferenceStack,
) -> None:
    change = preference_stack.service.record_expression(
        profile_id=preference_stack.profile_id,
        source_message_id=None,
        subject_key="balcon",
        raw_text="quiero balcón y que tenga buena luz",
        authority="explicit",
        binding_drafts=(
            BindingDraft.structured(
                concept_key="balcon",
                matcher_type="categorical",
                params={"preferred_value": True},
                confidence=0.95,
            ),
            BindingDraft.unresolved("sin_evidencia_luz"),
        ),
        correlation_id=uuid4(),
    )

    view = preference_stack.service.active_view(preference_stack.profile_id)
    with preference_stack.factory() as session:
        fact = session.scalar(
            select(PreferenceFact).where(
                PreferenceFact.id == change.fact_ids[0]
            )
        )
    assert [item.binding_kind for item in view] == ["structured", "unresolved"]
    assert fact is not None
    assert fact.criterion_binding_id == change.bindings[0].binding_id


def test_repository_persists_superseded_chain_in_one_mutation(
    preference_stack: PreferenceStack,
) -> None:
    original = preference_stack.service.record_expression(
        profile_id=preference_stack.profile_id,
        source_message_id=None,
        subject_key="balcon",
        raw_text="quiero balcón",
        authority="explicit",
        binding_drafts=(
            BindingDraft.structured(
                concept_key="balcon",
                matcher_type="categorical",
                params={"preferred_value": True},
                confidence=0.9,
            ),
            BindingDraft.unresolved("sin_otra_evidencia"),
        ),
        correlation_id=uuid4(),
    )
    revised = preference_stack.service.revise_expression(
        profile_id=preference_stack.profile_id,
        previous_expression_id=original.expression.expression_id,
        source_message_id=None,
        raw_text="prefiero sin balcón",
        authority="explicit",
        binding_drafts=(
            BindingDraft.structured(
                concept_key="balcon",
                matcher_type="categorical",
                params={"preferred_value": False},
                confidence=0.95,
            ),
        ),
        correlation_id=uuid4(),
    )

    retired_expression = preference_stack.expressions.get(
        original.expression.expression_id
    )
    with preference_stack.factory() as session:
        retired_bindings = {
            binding.id: binding
            for binding in session.scalars(
                select(CriterionBinding).where(
                    CriterionBinding.expression_id
                    == original.expression.expression_id
                )
            )
        }
    assert retired_expression is not None
    assert retired_expression.status == "superseded"
    assert retired_expression.superseded_by == revised.expression.expression_id
    assert retired_bindings[original.bindings[0].binding_id].superseded_by == (
        revised.bindings[0].binding_id
    )
    assert retired_bindings[original.bindings[1].binding_id].superseded_by is None


def test_set_explicit_preference_supersedes_the_prior_binding_and_fact(
    preference_stack: PreferenceStack,
) -> None:
    """Replacing low with essential leaves exactly one active fact lineage."""
    low = preference_stack.service.set_explicit_preference(
        profile_id=preference_stack.profile_id,
        source_message_id=None,
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
    essential = preference_stack.service.set_explicit_preference(
        profile_id=preference_stack.profile_id,
        source_message_id=None,
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

    with preference_stack.factory() as session:
        old_binding = session.get(CriterionBinding, low.bindings[0].binding_id)
        old_fact = session.get(PreferenceFact, low.fact_ids[0])
        new_fact = session.get(PreferenceFact, essential.fact_ids[0])

    assert old_binding is not None
    assert old_binding.status == "superseded"
    assert old_binding.superseded_by == essential.bindings[0].binding_id
    assert old_fact is not None
    assert old_fact.state == "superseded"
    assert old_fact.superseded_by == essential.fact_ids[0]
    assert new_fact is not None
    assert new_fact.state == "active"
    assert new_fact.criterion_binding_id == essential.bindings[0].binding_id


def test_repository_rolls_back_expression_and_bindings_when_fact_insert_fails(
    preference_stack: PreferenceStack,
) -> None:
    with pytest.raises(IntegrityError):
        preference_stack.service.record_expression(
            profile_id=preference_stack.profile_id,
            source_message_id=None,
            subject_key="balcon_doble",
            raw_text="quiero dos interpretaciones de balcón",
            authority="explicit",
            binding_drafts=(
                BindingDraft.structured(
                    concept_key="balcon",
                    matcher_type="categorical",
                    params={"preferred_value": True},
                    confidence=0.8,
                ),
                BindingDraft.structured(
                    concept_key="balcon",
                    matcher_type="categorical",
                    params={"preferred_value": False},
                    confidence=0.7,
                ),
            ),
            correlation_id=uuid4(),
        )

    with preference_stack.factory() as session:
        expression_count = session.scalar(
            select(func.count(PreferenceExpression.id)).where(
                PreferenceExpression.profile_id == preference_stack.profile_id,
                PreferenceExpression.subject_key == "balcon_doble",
            )
        )
        binding_count = session.scalar(
            select(func.count(CriterionBinding.id))
            .join(PreferenceExpression)
            .where(
                PreferenceExpression.profile_id == preference_stack.profile_id,
                PreferenceExpression.subject_key == "balcon_doble",
            )
        )
        fact_count = session.scalar(
            select(func.count(PreferenceFact.id)).where(
                PreferenceFact.profile_id == preference_stack.profile_id
            )
        )
    assert (expression_count, binding_count, fact_count) == (0, 0, 0)


def test_semantic_vectors_are_loaded_only_through_scoring_reader(
    preference_stack: PreferenceStack,
) -> None:
    vector = (0.25,) * 1536
    change = preference_stack.service.record_expression(
        profile_id=preference_stack.profile_id,
        source_message_id=None,
        subject_key="parque",
        raw_text="cerca de un parque",
        authority="explicit",
        binding_drafts=(
            BindingDraft.semantic(
                query_embedding=vector,
                embedding_version_id=preference_stack.embedding_version_id,
                confidence=0.6,
            ),
        ),
        correlation_id=uuid4(),
    )

    view = preference_stack.service.active_view(preference_stack.profile_id)
    semantic = preference_stack.bindings.active_semantic_for_profile_version(
        preference_stack.profile_version_id
    )
    assert not hasattr(view[0], "query_embedding")
    assert semantic[0].binding_id == change.bindings[0].binding_id
    assert semantic[0].query_embedding == vector
