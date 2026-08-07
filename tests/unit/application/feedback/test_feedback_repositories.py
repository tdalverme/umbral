"""In-memory feedback repository guard behaviors (chain, idempotency, ordering)."""
# ruff: noqa: E501

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from tests.fakes.feedback import (
    FakeFeedbackEventRepository,
    FakeLearningPolicyRepository,
    FakeLearningProposalRepository,
    FakeShortlistPort,
)

from umbral.application.feedback.contracts import (
    FeedbackEvent,
    LearningProposal,
    ProposalChange,
)

NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


def _event(
    *,
    event_type: str,
    listing_id: UUID,
    profile_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> FeedbackEvent:
    return FeedbackEvent(
        event_id=uuid4(),
        profile_id=profile_id or uuid4(),
        listing_id=listing_id,
        run_id=None,
        event_type=event_type,  # type: ignore[arg-type]
        state="active",
        superseded_by=None,
        idempotency_key=idempotency_key or str(uuid4()),
        reasons=(),
        free_feedback=None,
        created_at=NOW,
        correlation_id=uuid4(),
    )


def test_record_supersedes_the_active_event_in_place() -> None:
    repository = FakeFeedbackEventRepository()
    profile = uuid4()
    listing = uuid4()
    first = _event(event_type="like", listing_id=listing, profile_id=profile)
    second = _event(event_type="dislike", listing_id=listing, profile_id=profile)
    repository.record(first, None)
    repository.record(second, first)
    active = repository.active_state(profile, listing)
    assert active is not None
    assert active.event_type == "dislike"
    assert active.superseded_by is None
    superseded = next(
        item for item in repository.rows if item.event_id == first.event_id
    )
    assert superseded.state == "superseded"
    assert superseded.superseded_by == second.event_id


def test_idempotency_key_lookup_returns_the_original_event() -> None:
    repository = FakeFeedbackEventRepository()
    listing = uuid4()
    event = _event(event_type="save", listing_id=listing, idempotency_key="k1")
    repository.record(event, None)
    found = repository.get_by_idempotency(event.profile_id, "k1")
    assert found is not None and found.event_id == event.event_id
    assert repository.get_by_idempotency(event.profile_id, "k2") is None


def test_active_state_is_unique_per_listing() -> None:
    repository = FakeFeedbackEventRepository()
    profile = uuid4()
    listing = uuid4()
    first = _event(event_type="save", listing_id=listing, profile_id=profile)
    second = _event(event_type="dismiss", listing_id=listing, profile_id=profile)
    repository.record(first, None)
    repository.record(second, first)
    actives = repository.active_for_profile(profile)
    assert len(actives) == 1
    assert actives[0].event_id == second.event_id


def test_list_for_profile_filters_and_paginates() -> None:
    repository = FakeFeedbackEventRepository()
    profile = uuid4()
    for event_type in ("save", "dismiss", "save"):
        listing = uuid4()
        event = _event(event_type=event_type, listing_id=listing, profile_id=profile)
        event = FeedbackEvent(
            event_id=event.event_id,
            profile_id=profile,
            listing_id=listing,
            run_id=None,
            event_type=event.event_type,
            state="active",
            superseded_by=None,
            idempotency_key=event.idempotency_key,
            reasons=(),
            free_feedback=None,
            created_at=NOW + timedelta(minutes=1),
            correlation_id=event.correlation_id,
        )
        repository.record(event, None)
    saved, next_after = repository.list_for_profile(profile, "save", None, 10)
    assert len(saved) == 2
    assert next_after is None
    dismissed, _ = repository.list_for_profile(profile, "dismiss", None, 10)
    assert len(dismissed) == 1


def test_shortlist_port_add_remove_is_idempotent() -> None:
    port = FakeShortlistPort()
    profile = uuid4()
    listing = uuid4()
    port.add(profile, listing, NOW)
    port.add(profile, listing, NOW)
    assert port.list_for_profile(profile) == (listing,)
    port.remove(profile, listing)
    assert port.list_for_profile(profile) == ()


def test_policy_repository_registers_append_only_versions() -> None:
    repository = FakeLearningPolicyRepository()
    payload = {"contract_version": "1", "learning_policy_version": "learning-v1"}
    repository.register_version(
        policy_key="learning-v1",
        policy_version=1,
        contract_version="1",
        payload=payload,
        correlation_id=uuid4(),
        now=NOW,
    )
    repository.register_version(
        policy_key="learning-v1",
        policy_version=2,
        contract_version="1",
        payload=payload,
        correlation_id=uuid4(),
        now=NOW,
    )
    latest = repository.latest_version("learning-v1")
    assert latest is not None and latest.policy_version == 2
    assert len(repository.rows["learning-v1"]) == 2


def _proposal(*, profile_id: UUID, concept_id: UUID, state: str = "pending") -> LearningProposal:
    return LearningProposal(
        proposal_id=uuid4(),
        profile_id=profile_id,
        concept_id=concept_id,
        concept_key="ambientes",
        policy_version_id=uuid4(),
        policy_version="1",
        change=ProposalChange(
            kind="preference_fact",
            concept_key="ambientes",
            polarity="negative",
            suggested_weight=0.3,
            suggested_confidence=0.6,
            value=None,
        ),
        prior_fact=None,
        evidence_refs=(),
        state=state,  # type: ignore[arg-type]
        expires_at=NOW + timedelta(days=30),
        superseded_by=None,
        applied_profile_version_id=None,
        applied_run_id=None,
        created_at=NOW,
        correlation_id=uuid4(),
    )


def test_proposal_repository_filters_by_state_and_updates_in_place() -> None:
    from dataclasses import replace

    repository = FakeLearningProposalRepository()
    profile = uuid4()
    pending = _proposal(profile_id=profile, concept_id=uuid4())
    rejected = _proposal(profile_id=profile, concept_id=uuid4(), state="rejected")
    repository.insert(pending)
    repository.insert(rejected)
    pendings, _ = repository.list_for_profile(profile, "pending", None, 10)
    assert len(pendings) == 1
    repository.update(replace(pending, state="confirmed"))
    updated = repository.get(pending.proposal_id)
    assert updated is not None and updated.state == "confirmed"
