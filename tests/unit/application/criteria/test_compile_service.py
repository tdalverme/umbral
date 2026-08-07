"""US2: compilation service persistence, warnings, confirmations and events."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from tests.support.criteria import CriteriaTestContext

from umbral.application.criteria.contracts import (
    CriteriaNotFound,
    SoftToHardRequiresConfirmation,
)


def _profile(context: CriteriaTestContext) -> tuple[UUID, UUID, UUID]:
    profile_id = uuid4()
    owner_id = uuid4()
    version_id = uuid4()
    context.profiles.owners[profile_id] = owner_id
    context.profiles.versions[version_id] = (profile_id, 1)
    context.profiles.payloads[version_id] = {
        "name": "Mi radar",
        "zones": ["Caballito"],
        "budget_max": 500000.0,
    }
    return owner_id, profile_id, version_id


def test_compile_profile_persists_ordered_criteria_and_event() -> None:
    context = CriteriaTestContext()
    context.seed_concepts()
    owner_id, profile_id, version_id = _profile(context)
    context.service.record_preference_fact(
        owner_id=owner_id,
        profile_id=profile_id,
        concept_key="balcon",
        value="true",
        weight=0.8,
        polarity="positive",
        confidence=0.9,
        fact_source="harness",
        correlation_id=uuid4(),
    )
    compilation = context.service.compile_profile(
        owner_id=owner_id,
        profile_id=profile_id,
        profile_version_id=version_id,
        edits=(),
        correlation_id=uuid4(),
    )
    assert compilation.compilation_version == 1
    assert [criterion.concept_key for criterion in compilation.criteria] == ["balcon"]
    event = next(
        item
        for item in context.events.events
        if item.event_type == "criteria.compilation_created.v1"
    )
    assert event.payload["criterion_count"] == 1
    assert event.payload["compilation_version"] == 1


def test_compile_profile_recompilation_versions_increment() -> None:
    context = CriteriaTestContext()
    context.seed_concepts()
    owner_id, profile_id, version_id = _profile(context)
    first = context.service.compile_profile(
        owner_id=owner_id,
        profile_id=profile_id,
        profile_version_id=version_id,
        edits=(),
        correlation_id=uuid4(),
    )
    second = context.service.compile_profile(
        owner_id=owner_id,
        profile_id=profile_id,
        profile_version_id=version_id,
        edits=(),
        correlation_id=uuid4(),
    )
    assert first.compilation_version == 1
    assert second.compilation_version == 2


def test_compile_profile_soft_to_hard_requires_confirmation() -> None:
    context = CriteriaTestContext()
    context.seed_concepts()
    owner_id, profile_id, version_id = _profile(context)
    with pytest.raises(SoftToHardRequiresConfirmation):
        context.service.compile_profile(
            owner_id=owner_id,
            profile_id=profile_id,
            profile_version_id=version_id,
            edits=(
                {
                    "concept_key": "balcon",
                    "matcher_type": "categorical",
                    "params": {"allowed_values": ["true"]},
                    "source_ref": "fact:x",
                    "soft_to_hard": True,
                },
            ),
            confirmations=(),
            correlation_id=uuid4(),
        )
    compilation = context.service.compile_profile(
        owner_id=owner_id,
        profile_id=profile_id,
        profile_version_id=version_id,
        edits=(
            {
                "concept_key": "balcon",
                "matcher_type": "categorical",
                "params": {"allowed_values": ["true"]},
                "source_ref": "fact:x",
                "soft_to_hard": True,
            },
        ),
        confirmations=("balcon",),
        correlation_id=uuid4(),
    )
    assert compilation.criteria[0].soft_to_hard is True
    assert compilation.confirmations == ("balcon",)


def test_compile_profile_requires_ownership_and_version() -> None:
    context = CriteriaTestContext()
    context.seed_concepts()
    owner_id, profile_id, version_id = _profile(context)
    with pytest.raises(CriteriaNotFound):
        context.service.compile_profile(
            owner_id=uuid4(),
            profile_id=profile_id,
            profile_version_id=version_id,
            edits=(),
            correlation_id=uuid4(),
        )
    with pytest.raises(CriteriaNotFound):
        context.service.compile_profile(
            owner_id=owner_id,
            profile_id=profile_id,
            profile_version_id=uuid4(),
            edits=(),
            correlation_id=uuid4(),
        )
