"""SQLAlchemy repositories for the scoring domain.

Each method owns its commit, mirroring the radar/criteria repositories. The
atomic evaluation persistence happens inside ``RunRepository.publish``
(radar.py), so ``EvaluationRepository.insert_many`` exists only for in-memory
adapters and tests; the unique constraint
``uq_criterion_evaluations_run_listing_criterion`` arbitrates retries.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from umbral.application.criteria.contracts import ListingObservation
from umbral.application.ingestion.contracts import SourceIdentity
from umbral.application.scoring.contracts import (
    CriterionEvaluation,
    PolicyVersion,
)
from umbral.application.silver.contracts import GeoPrecision, NormalizedListing
from umbral.infrastructure.db.models.criteria import (
    ListingObservation as ListingObservationModel,
)
from umbral.infrastructure.db.models.scoring import (
    ComparisonShortlist as ComparisonShortlistModel,
)
from umbral.infrastructure.db.models.scoring import (
    CriterionEvaluation as CriterionEvaluationModel,
)
from umbral.infrastructure.db.models.scoring import (
    ScoringPolicy as ScoringPolicyModel,
)
from umbral.infrastructure.db.models.scoring import (
    ScoringPolicyVersion as ScoringPolicyVersionModel,
)
from umbral.infrastructure.db.models.silver import (
    SilverListing as SilverListingModel,
)

SessionFactory = Callable[[], Session]


class SqlAlchemyPolicyRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def register_version(
        self,
        *,
        policy_key: str,
        policy_version: int,
        contract_version: str,
        payload: Mapping[str, object],
        correlation_id: UUID,
        now: datetime,
    ) -> PolicyVersion:
        with self.session_factory() as session:
            policy = session.scalar(
                select(ScoringPolicyModel).where(
                    ScoringPolicyModel.policy_key == policy_key
                )
            )
            if policy is None:
                policy = ScoringPolicyModel(
                    id=uuid4(),
                    created_at=now,
                    updated_at=now,
                    actor_kind="service",
                    actor_id=None,
                    source="scoring.policy",
                    correlation_id=correlation_id,
                    policy_key=policy_key,
                    current_version_id=None,
                )
                session.add(policy)
                session.flush()
            model = ScoringPolicyVersionModel(
                id=uuid4(),
                created_at=now,
                updated_at=now,
                actor_kind="service",
                actor_id=None,
                source="scoring.policy",
                correlation_id=correlation_id,
                policy_id=policy.id,
                policy_version=policy_version,
                contract_version=contract_version,
                payload=dict(payload),
            )
            session.add(model)
            policy.current_version_id = model.id
            policy.updated_at = now
            session.commit()
            return PolicyVersion(
                version_id=model.id,
                policy_id=policy.id,
                policy_version=policy_version,
                contract_version=contract_version,
                payload=dict(payload),
                created_at=now,
                correlation_id=correlation_id,
            )

    def latest_version(self, policy_key: str) -> PolicyVersion | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(ScoringPolicyVersionModel)
                .join(
                    ScoringPolicyModel,
                    ScoringPolicyModel.id == ScoringPolicyVersionModel.policy_id,
                )
                .where(ScoringPolicyModel.policy_key == policy_key)
                .order_by(ScoringPolicyVersionModel.policy_version.desc())
                .limit(1)
            )
            return _to_domain_policy_version(model) if model is not None else None

    def get_version(self, version_id: UUID) -> PolicyVersion | None:
        with self.session_factory() as session:
            model = session.get(ScoringPolicyVersionModel, version_id)
            return _to_domain_policy_version(model) if model is not None else None


class SqlAlchemyEvaluationRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert_many(self, evaluations: tuple[CriterionEvaluation, ...]) -> None:
        with self.session_factory() as session:
            for evaluation in evaluations:
                session.add(_evaluation_model(evaluation))
            session.commit()

    def for_run(self, run_id: UUID) -> tuple[CriterionEvaluation, ...]:
        with self.session_factory() as session:
            models = session.scalars(
                select(CriterionEvaluationModel).where(
                    CriterionEvaluationModel.run_id == run_id
                )
            )
            return tuple(_to_domain_evaluation(model) for model in models)

    def for_run_and_listings(
        self, run_id: UUID, listing_ids: tuple[UUID, ...]
    ) -> Mapping[UUID, tuple[CriterionEvaluation, ...]]:
        if not listing_ids:
            return {}
        with self.session_factory() as session:
            models = session.scalars(
                select(CriterionEvaluationModel).where(
                    CriterionEvaluationModel.run_id == run_id,
                    CriterionEvaluationModel.listing_id.in_(listing_ids),
                )
            )
            by_listing: dict[UUID, list[CriterionEvaluation]] = {}
            for model in models:
                by_listing.setdefault(model.listing_id, []).append(
                    _to_domain_evaluation(model)
                )
            return {
                listing_id: tuple(sorted(items, key=lambda item: item.criterion_key))
                for listing_id, items in by_listing.items()
            }


class SqlAlchemyShortlistRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def replace(
        self,
        *,
        profile_id: UUID,
        listing_ids: tuple[UUID, ...],
        now: datetime,
        correlation_id: UUID,
    ) -> None:
        with self.session_factory() as session:
            session.query(ComparisonShortlistModel).filter(
                ComparisonShortlistModel.profile_id == profile_id
            ).delete()
            for position, listing_id in enumerate(listing_ids):
                session.add(
                    ComparisonShortlistModel(
                        id=uuid4(),
                        created_at=now,
                        updated_at=now,
                        actor_kind="service",
                        actor_id=None,
                        source="scoring.shortlist",
                        correlation_id=correlation_id,
                        profile_id=profile_id,
                        listing_id=listing_id,
                        position=position,
                    )
                )
            session.commit()

    def list_for_profile(self, profile_id: UUID) -> tuple[UUID, ...]:
        with self.session_factory() as session:
            models = session.scalars(
                select(ComparisonShortlistModel)
                .where(ComparisonShortlistModel.profile_id == profile_id)
                .order_by(ComparisonShortlistModel.position)
            )
            return tuple(model.listing_id for model in models)


class SqlAlchemyObservationReader:
    """Reads active observations for a batch of listing ids."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def active_for_listings(
        self, listing_ids: tuple[UUID, ...]
    ) -> Mapping[UUID, Mapping[str, ListingObservation]]:
        if not listing_ids:
            return {}
        with self.session_factory() as session:
            models = session.scalars(
                select(ListingObservationModel).where(
                    ListingObservationModel.listing_id.in_(listing_ids),
                    ListingObservationModel.state == "active",
                )
            )
            by_listing: dict[UUID, dict[str, ListingObservation]] = {}
            for model in models:
                by_listing.setdefault(model.listing_id, {})[model.concept_key] = (
                    _to_domain_observation(model)
                )
            return by_listing


class SqlAlchemyScoringListingReader:
    """Reads Silver listings by id for comparison assembly."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def _select(self) -> Any:
        from sqlalchemy import func

        return select(
            SilverListingModel,
            func.ST_Y(SilverListingModel.geometry).label("geo_lat"),
            func.ST_X(SilverListingModel.geometry).label("geo_lon"),
        )

    def get(self, listing_id: UUID) -> NormalizedListing | None:
        with self.session_factory() as session:
            row = session.execute(
                self._select().where(SilverListingModel.id == listing_id)
            ).first()
            return _to_domain_listing(tuple(row)) if row is not None else None

    def list_by_ids(
        self, listing_ids: tuple[UUID, ...]
    ) -> tuple[NormalizedListing, ...]:
        if not listing_ids:
            return ()
        with self.session_factory() as session:
            rows = session.execute(
                self._select().where(SilverListingModel.id.in_(listing_ids))
            )
            return tuple(_to_domain_listing(tuple(row)) for row in rows)


def _to_domain_policy_version(
    model: ScoringPolicyVersionModel,
) -> PolicyVersion:
    return PolicyVersion(
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


def _to_domain_evaluation(model: CriterionEvaluationModel) -> CriterionEvaluation:
    return CriterionEvaluation(
        evaluation_id=model.id,
        run_id=model.run_id,
        listing_id=model.listing_id,
        criterion_key=model.criterion_key,
        criterion_version=model.criterion_version,
        matcher_type=model.matcher_type,
        params=dict(model.params or {}),
        input_refs=tuple(model.input_refs or ()),
        score=float(model.score),
        confidence=float(model.confidence),
        state=model.state,  # type: ignore[arg-type]
        contribution=float(model.contribution),
        reason_code=model.reason_code,
        evidence_refs=tuple(model.evidence_refs or ()),
        created_at=model.created_at,
        correlation_id=model.correlation_id,
    )


def _evaluation_model(evaluation: CriterionEvaluation) -> CriterionEvaluationModel:
    return CriterionEvaluationModel(
        id=evaluation.evaluation_id,
        created_at=evaluation.created_at,
        updated_at=evaluation.created_at,
        actor_kind="service",
        actor_id=None,
        source="scoring.run",
        correlation_id=evaluation.correlation_id,
        run_id=evaluation.run_id,
        listing_id=evaluation.listing_id,
        criterion_key=evaluation.criterion_key,
        criterion_version=evaluation.criterion_version,
        matcher_type=evaluation.matcher_type,
        params=dict(evaluation.params),
        input_refs=[dict(ref) for ref in evaluation.input_refs],
        score=evaluation.score,
        confidence=evaluation.confidence,
        state=evaluation.state,
        contribution=evaluation.contribution,
        reason_code=evaluation.reason_code,
        evidence_refs=[dict(ref) for ref in evaluation.evidence_refs],
    )


def _to_domain_observation(model: ListingObservationModel) -> ListingObservation:
    return ListingObservation(
        observation_id=model.id,
        listing_id=model.listing_id,
        concept_key=model.concept_key,
        matcher_type=model.matcher_type,  # type: ignore[arg-type]
        value=model.value,
        score=float(model.score),
        confidence=float(model.confidence),
        evidence=dict(model.evidence or {}),
        source=model.source,  # type: ignore[arg-type]
        extraction_version_id=model.extraction_version_id,
        state=model.state,  # type: ignore[arg-type]
        failure_code=model.failure_code,
        recomputation_run_id=model.recomputation_run_id,
        created_at=model.created_at,
        correlation_id=model.correlation_id,
    )


def _to_domain_listing(row: tuple[object, ...]) -> NormalizedListing:
    model = cast(SilverListingModel, row[0])
    lat = cast(float | None, row[1])
    lon = cast(float | None, row[2])
    geometry = (float(lat), float(lon)) if lat is not None and lon is not None else None
    return NormalizedListing(
        listing_id=model.id,
        canonical_property_id=model.canonical_property_id,
        run_id=model.run_id,
        snapshot_id=model.snapshot_id,
        source=SourceIdentity(
            source_id=model.source_id,
            source_version=model.source_version,
            contract_version=model.contract_version,
        ),
        external_id=model.external_id,
        url=model.url,
        published_at=model.published_at,
        last_observed_at=model.last_observed_at,
        normalizer_version=model.normalizer_version,
        operation=model.operation,  # type: ignore[arg-type]
        property_type=model.property_type,  # type: ignore[arg-type]
        price_value=float(model.price_value),
        price_currency=model.price_currency,  # type: ignore[arg-type]
        expenses_value=(
            float(model.expenses_value) if model.expenses_value is not None else None
        ),
        expenses_currency=model.expenses_currency,  # type: ignore[arg-type]
        total_cost=float(model.total_cost),
        price_assumptions=dict(model.price_assumptions or {}),
        surface_m2=(float(model.surface_m2) if model.surface_m2 is not None else None),
        rooms=model.rooms,
        bedrooms=model.bedrooms,
        floor=model.floor,
        amenities=tuple(model.amenities or []),
        description_text=model.description_text,
        location_text=model.location_text,
        neighborhood=model.neighborhood,
        geo_precision=cast(GeoPrecision, model.geo_precision),
        geometry=geometry,
        geo_source=model.geo_source,
        normalization_errors=tuple(model.normalization_errors or []),
    )
