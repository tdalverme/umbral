"""Atomic mutation and lineage tests for the preference service."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import uuid4

import pytest
from tests.fakes.preferences import FakeConceptReader, FakePreferenceStore

from umbral.application.preferences.contracts import (
    BindingDraft,
    HardConfirmationRef,
    PreferenceConcept,
    PreferencePolicySpec,
    PreferenceValidationError,
)
from umbral.application.preferences.service import PreferenceService


@pytest.fixture
def service() -> PreferenceService:
    store = FakePreferenceStore()
    return PreferenceService(
        expressions=store,
        bindings=store,
        mutations=store,
        concepts=FakeConceptReader(
            {
                "balcon": PreferenceConcept(
                    key="balcon", matcher_type="categorical", computable=True
                )
            }
        ),
        policy=PreferencePolicySpec.v1(),
        clock=lambda: datetime(2026, 8, 14, tzinfo=timezone.utc),
    )


def test_atomic_mutation_does_not_persist_partial_expression_on_failure(
    service: PreferenceService,
) -> None:
    store = cast(FakePreferenceStore, service.mutations)
    store.fail_next_mutation = True

    with pytest.raises(RuntimeError, match="injected preference mutation failure"):
        service.record_expression(
            profile_id=uuid4(),
            source_message_id=uuid4(),
            subject_key="cocina_grande",
            raw_text="quiero una cocina grande",
            authority="explicit",
            binding_drafts=(BindingDraft.unresolved("no_evidence"),),
            correlation_id=uuid4(),
        )

    assert store.expressions == []
    assert store.bindings == []
    assert store.commands == []


def test_revision_maps_reordered_successors_and_retired_binding(
    service: PreferenceService,
) -> None:
    profile_id = uuid4()
    original = service.record_expression(
        profile_id=profile_id,
        source_message_id=uuid4(),
        subject_key="balcon",
        raw_text="quiero balcon y cerca de un parque",
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
                confidence=0.6,
            ),
            BindingDraft.unresolved("no_cafe_evidence"),
        ),
        correlation_id=uuid4(),
    )
    old_by_kind = {binding.kind: binding for binding in original.bindings}

    revised = service.revise_expression(
        profile_id=profile_id,
        previous_expression_id=original.expression.expression_id,
        source_message_id=uuid4(),
        raw_text="quiero cerca de un parque y balcon",
        authority="explicit",
        binding_drafts=(
            BindingDraft.semantic(
                query_embedding=(0.3, 0.4),
                embedding_version_id=uuid4(),
                confidence=0.6,
            ),
            BindingDraft.structured(
                concept_key="balcon",
                matcher_type="categorical",
                params={"preferred_value": True},
                confidence=0.9,
            ),
        ),
        correlation_id=uuid4(),
    )
    new_by_kind = {binding.kind: binding for binding in revised.bindings}
    store = cast(FakePreferenceStore, service.mutations)
    retired = {binding.binding_id: binding for binding in store.bindings}

    assert retired[old_by_kind["structured"].binding_id].superseded_by == new_by_kind[
        "structured"
    ].binding_id
    assert retired[old_by_kind["semantic"].binding_id].superseded_by == new_by_kind[
        "semantic"
    ].binding_id
    assert retired[old_by_kind["unresolved"].binding_id].superseded_by is None


def test_withdrawal_explicitly_retires_each_binding_without_successor(
    service: PreferenceService,
) -> None:
    created = service.record_expression(
        profile_id=uuid4(),
        source_message_id=uuid4(),
        subject_key="balcon",
        raw_text="quiero balcon y cerca de un parque",
        authority="explicit",
        binding_drafts=(
            BindingDraft.structured(
                concept_key="balcon",
                matcher_type="categorical",
                params={"preferred_value": True},
                confidence=0.9,
            ),
            BindingDraft.unresolved("no_park_evidence"),
        ),
        correlation_id=uuid4(),
    )

    service.withdraw_expression(
        profile_id=created.expression.profile_id,
        expression_id=created.expression.expression_id,
        correlation_id=uuid4(),
    )

    store = cast(FakePreferenceStore, service.mutations)
    retired = {binding.binding_id: binding for binding in store.bindings}
    assert all(
        retired[binding.binding_id].superseded_by is None
        for binding in created.bindings
    )


def test_confirmed_hard_structured_binding_produces_fact_with_auditable_ref(
    service: PreferenceService,
) -> None:
    confirmation = HardConfirmationRef(action_id=uuid4())

    change = service.record_expression(
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
                confirmation=confirmation,
            ),
        ),
        correlation_id=uuid4(),
    )

    assert len(change.fact_ids) == 1
    assert change.bindings[0].evidence_refs[-1] == {
        "kind": "hard_confirmation",
        "action_id": str(confirmation.action_id),
    }


def test_passive_authority_cannot_create_hard_binding(
    service: PreferenceService,
) -> None:
    with pytest.raises(PreferenceValidationError) as raised:
        service.record_expression(
            profile_id=uuid4(),
            source_message_id=uuid4(),
            subject_key="balcon",
            raw_text="parece que exige balcon",
            authority="passive",
            binding_drafts=(
                BindingDraft.structured(
                    concept_key="balcon",
                    matcher_type="categorical",
                    params={"preferred_value": True},
                    confidence=0.9,
                    mode="hard",
                    confirmation=HardConfirmationRef(action_id=uuid4()),
                ),
            ),
            correlation_id=uuid4(),
        )

    assert raised.value.error_codes == ("preferences.passive_hard_binding_forbidden",)
