"""US2: preference facts with supersession and deny-by-default."""

from __future__ import annotations

from uuid import uuid4

import pytest
from tests.support.criteria import CriteriaTestContext

from umbral.application.criteria.contracts import (
    CriteriaNotFound,
    CriteriaValidationError,
)


def test_record_preference_fact_persists_and_supersedes() -> None:
    context = CriteriaTestContext()
    context.seed_concepts()
    profile_id = uuid4()
    owner_id = uuid4()
    context.profiles.owners[profile_id] = owner_id
    first = context.service.record_preference_fact(
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
    second = context.service.record_preference_fact(
        owner_id=owner_id,
        profile_id=profile_id,
        concept_key="balcon",
        value="false",
        weight=0.6,
        polarity="negative",
        confidence=0.7,
        fact_source="harness",
        correlation_id=uuid4(),
    )
    active = context.facts.active_for_profile(profile_id)
    assert [fact.fact_id for fact in active] == [second.fact_id]
    superseded = [fact for fact in context.facts.rows if fact.fact_id == first.fact_id]
    assert len(superseded) == 1
    assert superseded[0].state == "superseded"
    assert superseded[0].superseded_by == second.fact_id


def test_fact_requires_ownership() -> None:
    context = CriteriaTestContext()
    context.seed_concepts()
    profile_id = uuid4()
    context.profiles.owners[profile_id] = uuid4()
    with pytest.raises(CriteriaNotFound):
        context.service.record_preference_fact(
            owner_id=uuid4(),
            profile_id=profile_id,
            concept_key="balcon",
            value="true",
            weight=0.8,
            polarity="positive",
            confidence=0.9,
            fact_source="harness",
            correlation_id=uuid4(),
        )


def test_fact_requires_existing_concept_and_bounded_values() -> None:
    context = CriteriaTestContext()
    context.seed_concepts()
    profile_id = uuid4()
    owner_id = uuid4()
    context.profiles.owners[profile_id] = owner_id
    with pytest.raises(CriteriaValidationError):
        context.service.record_preference_fact(
            owner_id=owner_id,
            profile_id=profile_id,
            concept_key="no_existe",
            value="true",
            weight=0.8,
            polarity="positive",
            confidence=0.9,
            fact_source="harness",
            correlation_id=uuid4(),
        )
    with pytest.raises(CriteriaValidationError):
        context.service.record_preference_fact(
            owner_id=owner_id,
            profile_id=profile_id,
            concept_key="balcon",
            value="true",
            weight=1.5,
            polarity="positive",
            confidence=0.9,
            fact_source="harness",
            correlation_id=uuid4(),
        )
    with pytest.raises(CriteriaValidationError):
        context.service.record_preference_fact(
            owner_id=owner_id,
            profile_id=profile_id,
            concept_key="balcon",
            value="true",
            weight=0.8,
            polarity="neutral",
            confidence=0.9,
            fact_source="harness",
            correlation_id=uuid4(),
        )
