# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type"
"""Concept feedback e2e over Postgres: reasons rows, signals, proposal, confirm.

Covers ADR 0003 FR-001..FR-005: interpreted concept feedback persists reasons
with strength/confidence, feeds the deterministic learning engine (never
auto-applies) and the confirm path versions the radar and schedules a run.
"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from tests.integration.feedback.conftest import (
    build_feedback,
    build_radar,
    seed_concepts,
    seed_profile,
    seed_user,
)

from umbral.infrastructure.db.models.feedback import FeedbackEventReason


def test_concept_feedback_reasons_persist_with_strength_and_confidence(
    feedback_backend,
) -> None:
    user_id = seed_user(feedback_backend)
    seed_concepts(feedback_backend)
    profile = seed_profile(feedback_backend, user_id)
    feedback = build_feedback(feedback_backend)
    owner_id, listing_id = user_id, uuid4()

    del listing_id
    feedback.record_feedback(
        owner_id=owner_id,
        profile_id=profile.profile_id,
        listing_id=uuid4(),
        run_id=None,
        event_type="dislike",
        reason_keys=(),
        idempotency_key="k-concept-1",
        correlation_id=uuid4(),
        concept_feedback=(
            {
                "concept_key": "tipo_cocina",
                "polarity": "negative",
                "strength": "strong",
                "confidence": 0.85,
            },
        ),
    )

    with feedback_backend() as session:
        rows = session.scalars(
            sa.select(FeedbackEventReason).where(
                FeedbackEventReason.reason_key == "concept:tipo_cocina"
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].polarity == "negative"
        assert rows[0].strength == "strong"
        assert rows[0].confidence == 0.85


def test_concept_feedback_confirms_proposal_and_reranks(
    feedback_backend,
) -> None:
    from tests.integration.feedback.conftest import build_criteria

    user_id = seed_user(feedback_backend)
    seed_concepts(feedback_backend)
    profile = seed_profile(feedback_backend, user_id)
    criteria = build_criteria(feedback_backend)
    radar = build_radar(feedback_backend)
    feedback = build_feedback(
        feedback_backend, radar=radar, criteria=criteria
    )

    first = feedback.record_feedback(
        owner_id=user_id,
        profile_id=profile.profile_id,
        listing_id=uuid4(),
        run_id=None,
        event_type="dislike",
        reason_keys=(),
        idempotency_key="k2-a",
        correlation_id=uuid4(),
        concept_feedback=(
            {
                "concept_key": "tipo_cocina",
                "polarity": "negative",
                "strength": "strong",
                "confidence": 0.9,
            },
        ),
    )
    assert first.learning_proposal_id is None

    second = feedback.record_feedback(
        owner_id=user_id,
        profile_id=profile.profile_id,
        listing_id=uuid4(),
        run_id=None,
        event_type="dislike",
        reason_keys=(),
        idempotency_key="k2-b",
        correlation_id=uuid4(),
        concept_feedback=(
            {
                "concept_key": "tipo_cocina",
                "polarity": "negative",
                "strength": "medium",
                "confidence": 0.6,
            },
        ),
    )
    assert second.learning_proposal_id is not None
    proposal = feedback.get_proposal(
        owner_id=user_id,
        profile_id=profile.profile_id,
        proposal_id=second.learning_proposal_id,
    )
    assert proposal.state == "pending"
    assert proposal.change.concept_key == "tipo_cocina"

    result = feedback.confirm_proposal(
        owner_id=user_id,
        profile_id=profile.profile_id,
        proposal_id=proposal.proposal_id,
        correlation_id=uuid4(),
    )
    assert result.applied_profile_version == 3
    assert result.run_id is not None

    facts = feedback.active_preferences(
        owner_id=user_id, profile_id=profile.profile_id
    )
    assert any(fact.concept_key == "tipo_cocina" for fact in facts)