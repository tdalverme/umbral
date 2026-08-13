"""US1: concept registry versioning with automatic invalidation and events."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from tests.support.criteria import CriteriaTestContext

from umbral.application.criteria.contracts import (
    CriteriaValidationError,
    ListingObservation,
    RecomputeScope,
)


def _observation(
    concept_key: str, listing_id: UUID | None = None, state: str = "active"
) -> ListingObservation:
    from datetime import datetime, timezone

    return ListingObservation(
        observation_id=uuid4(),
        listing_id=listing_id or uuid4(),
        concept_key=concept_key,
        matcher_type="categorical",
        value="true",
        score=1.0,
        confidence=1.0,
        evidence={"fragment": "f", "span": None, "matched_on": []},
        source="rule",
        extraction_version_id=None,
        state=state,  # type: ignore[arg-type]
        failure_code=None,
        recomputation_run_id=None,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        correlation_id=uuid4(),
    )


def test_seed_registry_is_idempotent_and_versioned() -> None:
    context = CriteriaTestContext()
    first = context.service.seed_registry(correlation_id=uuid4())
    second = context.service.seed_registry(correlation_id=uuid4())
    assert first == 10
    assert second == 0
    concept = context.concepts.get("balcon")
    assert concept is not None
    assert concept.current_version_id is not None
    assert len(context.concepts.versions) == 10


def test_register_concept_version_creates_new_immutable_version() -> None:
    context = CriteriaTestContext()
    context.seed_concepts()
    concept = context.concepts.get("balcon")
    assert concept is not None
    version = context.service.register_concept_version(
        key="balcon",
        name="Balcon amplio",
        aliases=("balcon",),
        matcher_type="categorical",
        params_schema={"allowed_values": ["true", "false"]},
        defaults={"value": "false"},
        compute_policy={"unknown": "penalize", "qualitative": False},
        correlation_id=uuid4(),
    )
    assert version.concept_version == 2
    updated = context.concepts.get("balcon")
    assert updated is not None
    assert updated.name == "Balcon amplio"
    versions = [item.concept_version for item in context.concepts.versions]
    assert versions == [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2]
    events = [
        item
        for item in context.events.events
        if item.event_type == "criteria.concept_version_created.v1"
    ]
    assert events[-1].payload == {"concept_key": "balcon", "concept_version": 2}


def test_register_concept_version_invalidates_affected_observations() -> None:
    context = CriteriaTestContext()
    context.seed_concepts()
    context.add_listing(description_text="con balcon")
    context.service.process_extraction(
        RecomputeScope("concept", "balcon"), job_execution_id=uuid4()
    )
    assert (
        sum(
            1
            for item in context.observations.rows
            if item.concept_key == "balcon" and item.state == "active"
        )
        == 1
    )
    context.service.register_concept_version(
        key="balcon",
        name="Balcon v2",
        aliases=("balcon",),
        matcher_type="categorical",
        params_schema={"allowed_values": ["true", "false"]},
        defaults={"value": "false"},
        compute_policy={"unknown": "penalize", "qualitative": False},
        correlation_id=uuid4(),
    )
    affected = [
        item for item in context.observations.rows if item.concept_key == "balcon"
    ]
    assert len(affected) == 1
    assert affected[0].state == "invalidated"


def test_invalid_concept_registration_is_rejected_without_partials() -> None:
    context = CriteriaTestContext()
    context.seed_concepts()
    with pytest.raises(CriteriaValidationError):
        context.service.register_concept_version(
            key="malo",
            name="Malo",
            aliases=(),
            matcher_type="matcher_no_soportado",
            params_schema={},
            defaults={},
            compute_policy={"unknown": "exclude", "qualitative": False},
            correlation_id=uuid4(),
        )
    assert context.concepts.get("malo") is None
    assert len(context.concepts.versions) == 10
