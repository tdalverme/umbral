"""SQLAlchemy repositories for the feedback domain.

Each method owns its commit, mirroring the radar/scoring repositories. The
feedback event chain is append-only: a decision change supersedes the active
row and inserts a new one in the same transaction; the partial unique
``uq_feedback_events_active`` arbitrates races.
"""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from umbral.application.feedback.contracts import (
    FeedbackEvent,
    LearningPolicyVersion,
    LearningProposal,
    ProposalChange,
    ReasonRef,
)
from umbral.infrastructure.db.models.feedback import (
    FeedbackEvent as FeedbackEventModel,
)
from umbral.infrastructure.db.models.feedback import (
    FeedbackEventReason as FeedbackEventReasonModel,
)
from umbral.infrastructure.db.models.feedback import (
    LearningPolicy as LearningPolicyModel,
)
from umbral.infrastructure.db.models.feedback import (
    LearningPolicyVersion as LearningPolicyVersionModel,
)
from umbral.infrastructure.db.models.feedback import (
    LearningProposal as LearningProposalModel,
)

SessionFactory = Callable[[], Session]


class SqlAlchemyFeedbackEventRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def record(
        self, event: FeedbackEvent, superseded: FeedbackEvent | None
    ) -> FeedbackEvent:
        with self.session_factory() as session:
            if superseded is not None:
                model = session.get(FeedbackEventModel, superseded.event_id)
                if model is not None and model.state == "active":
                    model.state = "superseded"
                    model.superseded_by = event.event_id
                    model.updated_at = event.created_at
            session.add(_event_model(event))
            session.flush()
            for reason in event.reasons:
                concept_id = None
                if reason.concept_key is not None:
                    concept_id = _concept_id(session, reason.concept_key)
                session.add(
                    FeedbackEventReasonModel(
                        id=uuid4(),
                        created_at=event.created_at,
                        updated_at=event.created_at,
                        actor_kind=event.actor_kind,
                        actor_id=event.actor_id,
                        source="feedback.event",
                        correlation_id=event.correlation_id,
                        event_id=event.event_id,
                        reason_key=reason.reason_key,
                        concept_id=concept_id,
                        polarity=reason.polarity,
                    )
                )
            session.commit()
        return event

    def get_by_idempotency(
        self, profile_id: UUID, idempotency_key: str
    ) -> FeedbackEvent | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(FeedbackEventModel).where(
                    FeedbackEventModel.profile_id == profile_id,
                    FeedbackEventModel.idempotency_key == idempotency_key,
                )
            )
            return _to_domain_event(session, model) if model is not None else None

    def active_state(
        self, profile_id: UUID, listing_id: UUID
    ) -> FeedbackEvent | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(FeedbackEventModel).where(
                    FeedbackEventModel.profile_id == profile_id,
                    FeedbackEventModel.listing_id == listing_id,
                    FeedbackEventModel.state == "active",
                )
            )
            return _to_domain_event(session, model) if model is not None else None

    def active_for_profile(self, profile_id: UUID) -> tuple[FeedbackEvent, ...]:
        with self.session_factory() as session:
            models = session.scalars(
                select(FeedbackEventModel).where(
                    FeedbackEventModel.profile_id == profile_id,
                    FeedbackEventModel.state == "active",
                )
            )
            return tuple(_to_domain_event(session, model) for model in models)

    def signal_events_since(
        self, profile_id: UUID, concept_id: UUID, since: datetime
    ) -> tuple[FeedbackEvent, ...]:
        with self.session_factory() as session:
            rows = session.execute(
                select(FeedbackEventModel)
                .join(
                    FeedbackEventReasonModel,
                    FeedbackEventReasonModel.event_id == FeedbackEventModel.id,
                )
                .where(
                    FeedbackEventModel.profile_id == profile_id,
                    FeedbackEventModel.state == "active",
                    FeedbackEventModel.event_type.in_(("like", "dislike")),
                    FeedbackEventModel.created_at >= since,
                    FeedbackEventReasonModel.concept_id == concept_id,
                )
                .distinct()
            )
            models = list(rows.scalars().all())
            return tuple(_to_domain_event(session, model) for model in models)

    def list_for_profile(
        self,
        profile_id: UUID,
        decision_state: str | None,
        after: int | None,
        limit: int,
    ) -> tuple[tuple[FeedbackEvent, ...], int | None]:
        with self.session_factory() as session:
            query = select(FeedbackEventModel).where(
                FeedbackEventModel.profile_id == profile_id,
                FeedbackEventModel.state == "active",
            )
            if decision_state is not None:
                query = query.where(
                    FeedbackEventModel.event_type == decision_state
                )
            query = query.order_by(
                FeedbackEventModel.created_at.desc(), FeedbackEventModel.id
            ).offset(after or 0).limit(limit)
            models = session.scalars(query)
            events = tuple(_to_domain_event(session, model) for model in models)
            next_after = (after or 0) + len(events) if len(events) == limit else None
            return events, next_after


class SqlAlchemyLearningPolicyRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def register_version(
        self,
        *,
        policy_key: str,
        policy_version: int,
        contract_version: str,
        payload: object,
        correlation_id: UUID,
        now: datetime,
    ) -> LearningPolicyVersion:
        with self.session_factory() as session:
            policy = session.scalar(
                select(LearningPolicyModel).where(
                    LearningPolicyModel.policy_key == policy_key
                )
            )
            if policy is None:
                policy = LearningPolicyModel(
                    id=uuid4(),
                    created_at=now,
                    updated_at=now,
                    actor_kind="service",
                    actor_id=None,
                    source="feedback.learning_policy",
                    correlation_id=correlation_id,
                    policy_key=policy_key,
                    current_version_id=None,
                )
                session.add(policy)
                session.flush()
            model = LearningPolicyVersionModel(
                id=uuid4(),
                created_at=now,
                updated_at=now,
                actor_kind="service",
                actor_id=None,
                source="feedback.learning_policy",
                correlation_id=correlation_id,
                policy_id=policy.id,
                policy_version=policy_version,
                contract_version=contract_version,
                payload=dict(cast(Mapping[str, object], payload)),
            )
            session.add(model)
            policy.current_version_id = model.id
            policy.updated_at = now
            session.commit()
            return LearningPolicyVersion(
                version_id=model.id,
                policy_id=policy.id,
                policy_version=policy_version,
                contract_version=contract_version,
                payload=dict(model.payload or {}),
                created_at=now,
                correlation_id=correlation_id,
            )

    def latest_version(self, policy_key: str) -> LearningPolicyVersion | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(LearningPolicyVersionModel)
                .join(
                    LearningPolicyModel,
                    LearningPolicyModel.id == LearningPolicyVersionModel.policy_id,
                )
                .where(LearningPolicyModel.policy_key == policy_key)
                .order_by(LearningPolicyVersionModel.policy_version.desc())
                .limit(1)
            )
            return _to_domain_policy_version(model) if model is not None else None

    def get_version(self, version_id: UUID) -> LearningPolicyVersion | None:
        with self.session_factory() as session:
            model = session.get(LearningPolicyVersionModel, version_id)
            return _to_domain_policy_version(model) if model is not None else None


class SqlAlchemyLearningProposalRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert(self, proposal: LearningProposal) -> LearningProposal:
        with self.session_factory() as session:
            session.add(_proposal_model(proposal))
            session.commit()
        return proposal

    def get(self, proposal_id: UUID) -> LearningProposal | None:
        with self.session_factory() as session:
            model = session.get(LearningProposalModel, proposal_id)
            return _to_domain_proposal(model) if model is not None else None

    def pending_for_concept(
        self, profile_id: UUID, concept_id: UUID
    ) -> LearningProposal | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(LearningProposalModel).where(
                    LearningProposalModel.profile_id == profile_id,
                    LearningProposalModel.concept_id == concept_id,
                    LearningProposalModel.state == "pending",
                )
            )
            return _to_domain_proposal(model) if model is not None else None

    def recent_for_concept(
        self, profile_id: UUID, concept_id: UUID, since: datetime
    ) -> tuple[LearningProposal, ...]:
        with self.session_factory() as session:
            models = session.scalars(
                select(LearningProposalModel).where(
                    LearningProposalModel.profile_id == profile_id,
                    LearningProposalModel.concept_id == concept_id,
                    LearningProposalModel.created_at >= since,
                )
            )
            return tuple(_to_domain_proposal(model) for model in models)

    def list_for_profile(
        self,
        profile_id: UUID,
        state: str | None,
        after: int | None,
        limit: int,
    ) -> tuple[tuple[LearningProposal, ...], int | None]:
        with self.session_factory() as session:
            query = select(LearningProposalModel).where(
                LearningProposalModel.profile_id == profile_id
            )
            if state is not None:
                query = query.where(LearningProposalModel.state == state)
            query = query.order_by(
                LearningProposalModel.created_at.desc(), LearningProposalModel.id
            ).offset(after or 0).limit(limit)
            models = session.scalars(query)
            proposals = tuple(_to_domain_proposal(model) for model in models)
            next_after = (after or 0) + len(proposals) if len(proposals) == limit else None
            return proposals, next_after

    def update(self, proposal: LearningProposal) -> LearningProposal:
        with self.session_factory() as session:
            model = session.get(LearningProposalModel, proposal.proposal_id)
            if model is None:
                raise LookupError(f"proposal not found: {proposal.proposal_id}")
            model.change = dict(_change_payload(proposal.change))
            model.prior_fact = (
                dict(proposal.prior_fact) if proposal.prior_fact is not None else None
            )
            model.state = proposal.state
            model.expires_at = proposal.expires_at
            model.superseded_by = proposal.superseded_by
            model.applied_profile_version_id = proposal.applied_profile_version_id
            model.applied_run_id = proposal.applied_run_id
            session.commit()
        return proposal


def _event_model(event: FeedbackEvent) -> FeedbackEventModel:
    return FeedbackEventModel(
        id=event.event_id,
        created_at=event.created_at,
        updated_at=event.created_at,
        actor_kind=event.actor_kind,
        actor_id=event.actor_id,
        source="feedback.event",
        correlation_id=event.correlation_id,
        profile_id=event.profile_id,
        listing_id=event.listing_id,
        run_id=event.run_id,
        event_type=event.event_type,
        state=event.state,
        superseded_by=event.superseded_by,
        idempotency_key=event.idempotency_key,
        free_feedback=event.free_feedback,
    )


def _concept_id(session: Session, concept_key: str) -> UUID | None:
    from umbral.infrastructure.db.models.criteria import Concept as ConceptModel

    model = session.scalar(
        select(ConceptModel).where(ConceptModel.key == concept_key)
    )
    return model.id if model is not None else None


def _reasons(session: Session, event_id: UUID) -> tuple[ReasonRef, ...]:
    models = session.scalars(
        select(FeedbackEventReasonModel).where(
            FeedbackEventReasonModel.event_id == event_id
        )
    )
    return tuple(
        ReasonRef(
            reason_key=model.reason_key,
            polarity=model.polarity,  # type: ignore[arg-type]
            concept_key=_concept_key_of(session, model.concept_id),
        )
        for model in models
    )


def _concept_key_of(session: Session, concept_id: UUID | None) -> str | None:
    if concept_id is None:
        return None
    from umbral.infrastructure.db.models.criteria import Concept as ConceptModel

    model = session.get(ConceptModel, concept_id)
    return model.key if model is not None else None


def _to_domain_event(
    session: Session, model: FeedbackEventModel
) -> FeedbackEvent:
    return FeedbackEvent(
        event_id=model.id,
        profile_id=model.profile_id,
        listing_id=model.listing_id,
        run_id=model.run_id,
        event_type=model.event_type,  # type: ignore[arg-type]
        state=model.state,  # type: ignore[arg-type]
        superseded_by=model.superseded_by,
        idempotency_key=model.idempotency_key,
        reasons=_reasons(session, model.id),
        free_feedback=model.free_feedback,
        created_at=model.created_at,
        correlation_id=model.correlation_id,
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
    )


def _as_float(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _to_domain_policy_version(
    model: LearningPolicyVersionModel,
) -> LearningPolicyVersion:    return LearningPolicyVersion(
        version_id=model.id,
        policy_id=model.policy_id,
        policy_version=model.policy_version,
        contract_version=model.contract_version,
        payload=dict(model.payload or {}),
        created_at=model.created_at,
        correlation_id=model.correlation_id,
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
    )


def _proposal_model(proposal: LearningProposal) -> LearningProposalModel:
    return LearningProposalModel(
        id=proposal.proposal_id,
        created_at=proposal.created_at,
        updated_at=proposal.created_at,
        actor_kind=proposal.actor_kind,
        actor_id=proposal.actor_id,
        source="feedback.learning_proposal",
        correlation_id=proposal.correlation_id,
        profile_id=proposal.profile_id,
        concept_id=proposal.concept_id,
        concept_key=proposal.concept_key,
        policy_version_id=proposal.policy_version_id,
        policy_version=proposal.policy_version,
        change=dict(_change_payload(proposal.change)),
        prior_fact=dict(proposal.prior_fact) if proposal.prior_fact is not None else None,
        evidence_refs=[dict(ref) for ref in proposal.evidence_refs],
        state=proposal.state,
        expires_at=proposal.expires_at,
        superseded_by=proposal.superseded_by,
        applied_profile_version_id=proposal.applied_profile_version_id,
        applied_run_id=proposal.applied_run_id,
    )


def _change_payload(change: ProposalChange) -> Mapping[str, object]:
    return {
        "kind": change.kind,
        "concept_key": change.concept_key,
        "polarity": change.polarity,
        "suggested_weight": change.suggested_weight,
        "suggested_confidence": change.suggested_confidence,
        "value": change.value,
    }


def _to_domain_proposal(model: LearningProposalModel) -> LearningProposal:
    payload = cast(Mapping[str, object], model.change or {})
    return LearningProposal(
        proposal_id=model.id,
        profile_id=model.profile_id,
        concept_id=model.concept_id,
        concept_key=model.concept_key,
        policy_version_id=model.policy_version_id,
        policy_version=model.policy_version or "1",
        change=ProposalChange(
            kind="preference_fact",
            concept_key=str(payload.get("concept_key", model.concept_key)),
            polarity=str(payload.get("polarity", "negative")),
            suggested_weight=_as_float(payload.get("suggested_weight"), 0.3),
            suggested_confidence=_as_float(payload.get("suggested_confidence"), 0.6),
            value=payload.get("value"),
        ),
        prior_fact=dict(model.prior_fact) if model.prior_fact is not None else None,
        evidence_refs=tuple(model.evidence_refs or []),
        state=model.state,  # type: ignore[arg-type]
        expires_at=model.expires_at,
        superseded_by=model.superseded_by,
        applied_profile_version_id=model.applied_profile_version_id,
        applied_run_id=model.applied_run_id,
        created_at=model.created_at,
        correlation_id=model.correlation_id,
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
    )
