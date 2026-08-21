"""US4: elevating a criterion to hard supersedes learned hypotheses (FR-012/013)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from tests.support.feedback import NOW, FeedbackTestContext

from umbral.application.feedback.contracts import LearningProposal, ProposalChange


def _proposal(
    context: FeedbackTestContext,
    profile_id: object,
    concept_key: str,
    state: str = "pending",
) -> LearningProposal:
    concept_id = context.concepts.get(concept_key)
    assert concept_id is not None
    proposal = LearningProposal(
        proposal_id=uuid4(),
        profile_id=profile_id,  # type: ignore[arg-type]
        concept_id=concept_id[0],
        concept_key=concept_key,
        policy_version_id=uuid4(),
        policy_version="learning-v1",
        change=ProposalChange(
            kind="preference_fact",
            concept_key=concept_key,
            polarity="positive",
            suggested_weight=0.5,
            suggested_confidence=0.7,
            value=None,
        ),
        prior_fact=None,
        evidence_refs=(),
        state=state,  # type: ignore[arg-type]
        expires_at=datetime(2026, 8, 9, tzinfo=timezone.utc),
        superseded_by=None,
        applied_profile_version_id=None,
        applied_run_id=None,
        created_at=NOW,
        correlation_id=uuid4(),
    )
    context.proposals.insert(proposal)
    return proposal


def test_supersede_learning_for_concept_retires_the_concept_hypotheses() -> None:
    context = FeedbackTestContext()
    profile = context.add_profile()
    same = _proposal(context, profile.profile_id, "mascotas")
    unrelated = _proposal(context, profile.profile_id, "balcon")
    confirmed = _proposal(
        context, profile.profile_id, "mascotas", state="confirmed"
    )

    superseded = context.service.supersede_learning_for_concept(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        concept_key="mascotas",
        confirmation_ref=uuid4(),
        correlation_id=uuid4(),
    )

    assert superseded == 2
    states = {item.concept_key: item.state for item in context.proposals.rows}
    assert states[same.concept_key] == "superseded"
    assert states[confirmed.concept_key] == "superseded"
    assert states[unrelated.concept_key] == "pending"


def test_supersede_emits_hard_elevation_event() -> None:
    context = FeedbackTestContext()
    profile = context.add_profile()
    _proposal(context, profile.profile_id, "mascotas")
    confirmation = uuid4()

    context.service.supersede_learning_for_concept(
        owner_id=profile.owner_id,
        profile_id=profile.profile_id,
        concept_key="mascotas",
        confirmation_ref=confirmation,
        correlation_id=uuid4(),
    )

    events = [
        event
        for event in context.events_out.events
        if event.event_type == "preference.hard_elevated.v1"
    ]
    assert len(events) == 1
    assert events[0].payload["concept_key"] == "mascotas"
    assert events[0].payload["confirmation_ref"] == str(confirmation)
    assert events[0].payload["superseded_hypothesis_count"] == 1


def test_supersede_unknown_concept_is_rejected() -> None:
    context = FeedbackTestContext()
    profile = context.add_profile()
    try:
        context.service.supersede_learning_for_concept(
            owner_id=profile.owner_id,
            profile_id=profile.profile_id,
            concept_key="no_existe",
            confirmation_ref=uuid4(),
            correlation_id=uuid4(),
        )
    except Exception as error:
        assert "unknown_concept" in str(error)
    else:
        raise AssertionError("expected unknown concept rejection")
