"""Repository invariants for criteria entities (in-memory adapters)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import uuid4

from sqlalchemy.orm import Session
from tests.fakes.criteria import (
    FakeConceptRepository,
    FakeFactRepository,
    FakeObservationRepository,
)

from umbral.application.criteria.contracts import (
    Concept,
    ConceptVersion,
    ListingObservation,
    PreferenceFact,
    RecomputeScope,
)
from umbral.infrastructure.db.models.criteria import (
    PreferenceFact as PreferenceFactModel,
)
from umbral.infrastructure.db.repositories.criteria import SqlAlchemyFactRepository

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)
PROFILE_ID = uuid4()


def _concept(key: str = "balcon") -> Concept:
    return Concept(
        concept_id=uuid4(),
        key=key,
        name=key,
        aliases=(),
        matcher_type="categorical",
        params_schema={"allowed_values": ["true", "false"]},
        source="operator",
        defaults={"value": "false"},
        compute_policy={"unknown": "penalize", "qualitative": False},
        version=1,
        current_version_id=None,
        created_at=NOW,
        updated_at=NOW,
        correlation_id=uuid4(),
    )


def _version(concept: Concept, number: int) -> ConceptVersion:
    return ConceptVersion(
        version_id=uuid4(),
        concept_id=concept.concept_id,
        concept_version=number,
        payload=concept.payload(),
        created_at=NOW,
        correlation_id=uuid4(),
    )


def test_concept_repository_versioning_is_append_only() -> None:
    repo = FakeConceptRepository()
    concept = _concept()
    repo.insert(concept)
    repo.insert_version(_version(concept, 1))
    repo.insert_version(_version(concept, 2))
    assert repo.get("balcon") is not None
    latest = repo.latest_version(concept.concept_id)
    assert latest is not None
    assert latest.concept_version == 2
    assert len(repo.versions) == 2


def test_fact_repository_supersedes_the_active_fact() -> None:
    repo = FakeFactRepository()
    first = PreferenceFact(
        fact_id=uuid4(),
        profile_id=PROFILE_ID,
        concept_key="balcon",
        value="true",
        weight=0.8,
        polarity="positive",
        confidence=0.9,
        fact_source="harness",
        state="active",
        superseded_by=None,
        created_at=NOW,
        correlation_id=uuid4(),
    )
    repo.record_change(first, superseded_by=None)
    second = PreferenceFact(
        fact_id=uuid4(),
        profile_id=PROFILE_ID,
        concept_key="balcon",
        value="false",
        weight=0.6,
        polarity="negative",
        confidence=0.7,
        fact_source="harness",
        state="active",
        superseded_by=None,
        created_at=NOW.replace(microsecond=1),
        correlation_id=uuid4(),
    )
    repo.record_change(second, superseded_by=second.fact_id)
    active = repo.active_for_profile(PROFILE_ID)
    assert [fact.fact_id for fact in active] == [second.fact_id]
    assert active[0].superseded_by is None


def test_sql_fact_repository_reconstructs_replaced_fact_at_snapshot() -> None:
    snapshot_at = datetime(2026, 8, 2, tzinfo=timezone.utc)
    old_id = uuid4()
    profile_id = uuid4()
    old = PreferenceFactModel(
        id=old_id,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
        actor_kind="service",
        actor_id=None,
        source="criteria.fact",
        correlation_id=uuid4(),
        profile_id=profile_id,
        concept_key="balcon",
        value="true",
        weight=0.8,
        polarity="positive",
        confidence=0.9,
        fact_source="harness",
        state="superseded",
        superseded_by=uuid4(),
        soft_to_hard=False,
    )

    class _Session:
        def __enter__(self) -> _Session:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def scalars(self, statement: object) -> tuple[PreferenceFactModel, ...]:
            del statement
            return (old,)

    repository = SqlAlchemyFactRepository(lambda: cast(Session, _Session()))

    reconstructed = repository.active_for_profile_as_of(profile_id, snapshot_at)

    assert [fact.fact_id for fact in reconstructed] == [old_id]


def test_observation_repository_scopes_and_supersede() -> None:
    repo = FakeObservationRepository()
    listing_id = uuid4()
    first = ListingObservation(
        observation_id=uuid4(),
        listing_id=listing_id,
        concept_key="balcon",
        matcher_type="categorical",
        value="true",
        score=1.0,
        confidence=1.0,
        evidence={"fragment": "con balcon", "span": None, "matched_on": []},
        source="rule",
        extraction_version_id=None,
        state="active",
        failure_code=None,
        recomputation_run_id=None,
        created_at=NOW,
        correlation_id=uuid4(),
    )
    repo.publish((first,), supersede_ids=(), run=None, event=None)
    assert repo.invalidate_for_concept("balcon") == 1
    scope_ids = repo.ids_for_scope(RecomputeScope("concept", "balcon"))
    assert scope_ids == (first.observation_id,)
    replacement = ListingObservation(
        observation_id=uuid4(),
        listing_id=listing_id,
        concept_key="balcon",
        matcher_type="categorical",
        value="false",
        score=1.0,
        confidence=1.0,
        evidence={"fragment": "sin balcon", "span": None, "matched_on": []},
        source="rule",
        extraction_version_id=None,
        state="active",
        failure_code=None,
        recomputation_run_id=None,
        created_at=NOW,
        correlation_id=uuid4(),
    )
    repo.publish((replacement,), supersede_ids=scope_ids, run=None, event=None)
    states = {item.state for item in repo.rows}
    assert "superseded" in states
    assert sum(1 for item in repo.rows if item.state == "active") == 1


def test_recompute_scope_parse_and_target_round_trip() -> None:
    assert RecomputeScope.parse("full").target == "full"
    scope = RecomputeScope.parse("concept:balcon")
    assert scope.kind == "concept"
    assert scope.key == "balcon"
    assert scope.target == "concept:balcon"
