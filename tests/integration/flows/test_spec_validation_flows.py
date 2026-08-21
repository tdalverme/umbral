"""Golden path for the two validation flows described by SPEC.md."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from tests.integration.criteria.conftest import build_criteria_service
from tests.integration.feedback.conftest import (
    build_feedback,
    seed_concepts,
)
from tests.integration.scoring.conftest import build_scoring, seed_run
from tests.integration.urban.conftest import (
    run_urban_batch,
    seed_listing,
    seed_urban_category,
    seed_urban_snapshot,
)

from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.infrastructure.db.models.criteria import ListingObservation
from umbral.infrastructure.db.models.feedback import FeedbackEvent
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.infrastructure.radar.composition import build_radar_service


def _criterion_signature(explanation: Any, criterion_key: str) -> tuple[Any, ...]:
    for reason in explanation.reasons:
        if reason.criterion_key == criterion_key:
            return reason.state, reason.score, reason.contribution
    for risk in explanation.risks:
        if risk.criterion_key == criterion_key:
            return risk.state, risk.reason_code
    return ("missing", criterion_key)


def test_spec_validation_flows_are_persistent_and_reproducible(
    spec_validation_backend: Any,
) -> None:
    factory = spec_validation_backend

    # Flow A: imported Silver listings -> rule observations -> ranked run ->
    # deterministic explanation with internal evidence.
    urban_listing_id = seed_listing(
        factory,
        geometry=(-34.6, -58.42),
        neighborhood="Caballito",
    )
    urban_snapshot_id = seed_urban_snapshot(factory, poi_count=1)
    seed_urban_category(
        factory,
        urban_snapshot_id,
        category="cafe",
        osm_id="spec-019-cafe",
        lon=-58.42,
        lat=-34.6,
    )
    radar, profile, first_run = seed_run(factory)
    assert first_run is not None
    assert first_run.state == "succeeded"
    run_urban_batch(factory)
    first_page = radar.get_matches(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        run_id=first_run.run_id,
        after_position=None,
        limit=100,
    )
    assert first_page.items

    scoring = build_scoring(factory)
    first_explanations = {
        item.listing_id: scoring.get_explanation(
            owner_id=profile.owner_id,
            profile_id=profile.profile_id,
            run_id=first_run.run_id,
            listing_id=item.listing_id,
        )
        for item in first_page.items
    }
    top_explanation = first_explanations[first_page.items[0].listing_id]
    assert any(reason.evidence_refs for reason in top_explanation.reasons)

    with factory() as session:
        observation_sources = set(
            session.scalars(select(ListingObservation.source)).all()
        )
        assert "rule" in observation_sources
        assert "urban" in observation_sources
        assert urban_listing_id in set(
            session.scalars(
                select(ListingObservation.listing_id).where(
                    ListingObservation.source == "urban",
                    ListingObservation.state == "active",
                )
            ).all()
        )

    # Flow B: two consistent concept signals -> pending HITL proposal ->
    # confirmed fact and a new frozen run. The first event is replayed to prove
    # idempotency does not duplicate the signal.
    seed_concepts(factory)
    criteria = build_criteria_service(factory)
    recalculation_radar = build_radar_service(
        session_factory=factory,
        job_runtime=InMemoryJobRuntime(queue=RecordingJobQueue()),
        policy_engine=scoring,
        score_policy_version="scoring-policy-v1",
        clock=lambda: first_run.created_at,
    )
    feedback = build_feedback(
        factory,
        radar=recalculation_radar,
        criteria=criteria,
    )
    listing_ids = tuple(item.listing_id for item in first_page.items)
    first_feedback = feedback.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=listing_ids[0],
        run_id=first_run.run_id,
        event_type="dislike",
        reason_keys=(),
        idempotency_key="spec-019-feedback-1",
        correlation_id=uuid4(),
        concept_feedback=(
            {
                "concept_key": "balcon",
                "polarity": "negative",
                "strength": "strong",
                "confidence": 0.9,
            },
        ),
    )
    replay = feedback.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=listing_ids[0],
        run_id=first_run.run_id,
        event_type="dislike",
        reason_keys=(),
        idempotency_key="spec-019-feedback-1",
        correlation_id=uuid4(),
        concept_feedback=(
            {
                "concept_key": "balcon",
                "polarity": "negative",
                "strength": "strong",
                "confidence": 0.9,
            },
        ),
    )
    assert first_feedback.noop is False
    assert replay.noop is True

    second_feedback = feedback.record_feedback(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        listing_id=listing_ids[1],
        run_id=first_run.run_id,
        event_type="dislike",
        reason_keys=(),
        idempotency_key="spec-019-feedback-2",
        correlation_id=uuid4(),
        concept_feedback=(
            {
                "concept_key": "balcon",
                "polarity": "negative",
                "strength": "medium",
                "confidence": 0.6,
            },
        ),
    )
    assert second_feedback.learning_proposal_id is not None
    proposal = feedback.get_proposal(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        proposal_id=second_feedback.learning_proposal_id,
    )
    assert proposal.state == "pending"
    assert len(proposal.evidence_refs) == 2

    confirmed = feedback.confirm_proposal(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        proposal_id=proposal.proposal_id,
        correlation_id=uuid4(),
    )
    assert confirmed.proposal.state == "confirmed"
    assert confirmed.applied_profile_version >= 2
    assert confirmed.run_id is not None

    recalculation_radar.process_run(
        run_id=confirmed.run_id,
        job_execution_id=uuid4(),
    )
    second_page = recalculation_radar.get_matches(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        run_id=confirmed.run_id,
        after_position=None,
        limit=100,
    )
    assert second_page.run.state == "succeeded"
    assert [item.listing_id for item in second_page.items] != [
        item.listing_id for item in first_page.items
    ] or any(
        _criterion_signature(
            scoring.get_explanation(
                owner_id=profile.owner_id,
                profile_id=profile.profile_id,
                run_id=confirmed.run_id,
                listing_id=item.listing_id,
            ),
            "balcon",
        )
        != _criterion_signature(first_explanations[item.listing_id], "balcon")
        for item in second_page.items
    )

    with factory() as session:
        feedback_event_count = session.scalar(
            select(func.count()).select_from(FeedbackEvent)
        )
        assert feedback_event_count == 2
