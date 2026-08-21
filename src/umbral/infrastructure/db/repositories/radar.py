"""SQLAlchemy repositories for the structured search radar.

Each method owns its commit, mirroring the silver repositories. The atomic
``RunRepository.publish`` commits run success + items + run-published event in
one transaction; unique constraints arbitrate interrupted retries.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from umbral.application.events.contracts import ProductEvent
from umbral.application.ingestion.contracts import SourceIdentity
from umbral.application.radar.contracts import (
    ProfileVersion,
    RecommendationItem,
    RecommendationRun,
    SearchProfile,
    SearchProfileState,
)
from umbral.application.scoring.contracts import CriterionEvaluation
from umbral.application.silver.contracts import (
    ACTIVE_NORMALIZER_VERSION,
    GeoPrecision,
    NormalizedListing,
)
from umbral.domain.errors import ConcurrencyConflict
from umbral.infrastructure.db.models.radar import (
    ProductEventRow,
)
from umbral.infrastructure.db.models.radar import (
    RecommendationItem as RecommendationItemModel,
)
from umbral.infrastructure.db.models.radar import (
    RecommendationRun as RecommendationRunModel,
)
from umbral.infrastructure.db.models.radar import (
    SearchProfile as SearchProfileModel,
)
from umbral.infrastructure.db.models.radar import (
    SearchProfileVersion as SearchProfileVersionModel,
)
from umbral.infrastructure.db.models.scoring import (
    CriterionEvaluation as CriterionEvaluationModel,
)
from umbral.infrastructure.db.models.silver import (
    ListingChange as ListingChangeModel,
)
from umbral.infrastructure.db.models.silver import (
    SilverListing as SilverListingModel,
)

SessionFactory = Callable[[], Session]

_OPERATION = "rental"


class SqlAlchemySearchProfileRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert(self, profile: SearchProfile) -> None:
        with self.session_factory() as session:
            session.add(_profile_model(profile))
            session.commit()

    def insert_with_version(
        self,
        profile: SearchProfile,
        version: ProfileVersion,
        created_event: ProductEvent,
    ) -> None:
        with self.session_factory() as session:
            try:
                model = _profile_model(replace(profile, current_version_id=None))
                session.add(model)
                session.flush()
                session.add(_version_model(version))
                session.flush()
                session.add(
                    ProductEventRow(
                        id=created_event.event_id,
                        created_at=created_event.occurred_at,
                        updated_at=created_event.occurred_at,
                        actor_kind="service",
                        actor_id=(
                            str(created_event.actor_id)
                            if created_event.actor_id is not None
                            else None
                        ),
                        source="radar.events",
                        correlation_id=created_event.correlation_id,
                        event_type=created_event.event_type,
                        event_version=created_event.event_version,
                        occurred_at=created_event.occurred_at,
                        payload=dict(created_event.payload),
                    )
                )
                session.flush()
                session.execute(
                    update(SearchProfileModel)
                    .where(SearchProfileModel.id == profile.profile_id)
                    .values(current_version_id=profile.current_version_id)
                    .execution_options(synchronize_session=False)
                )
                session.commit()
            except IntegrityError as error:
                session.rollback()
                actual_version = _profile_version(session, profile.profile_id)
                raise ConcurrencyConflict(
                    expected_version=profile.version,
                    actual_version=actual_version,
                ) from error

    def get(self, profile_id: UUID) -> SearchProfile | None:
        with self.session_factory() as session:
            model = session.get(SearchProfileModel, profile_id)
            return _to_domain_profile(model) if model is not None else None

    def list_by_owner(
        self, owner_id: UUID, status: SearchProfileState | None
    ) -> tuple[SearchProfile, ...]:
        with self.session_factory() as session:
            statement = select(SearchProfileModel).where(
                SearchProfileModel.owner_id == owner_id
            )
            if status is not None:
                statement = statement.where(SearchProfileModel.status == status)
            statement = statement.order_by(SearchProfileModel.created_at.desc())
            models = session.scalars(statement)
            return tuple(_to_domain_profile(model) for model in models)

    def save(self, profile: SearchProfile) -> None:
        with self.session_factory() as session:
            model = session.get(SearchProfileModel, profile.profile_id)
            if model is None:
                raise KeyError(profile.profile_id)
            if model.version != profile.version:
                raise ConcurrencyConflict(
                    expected_version=profile.version, actual_version=model.version
                )
            _update_profile_model(model, profile)
            try:
                session.commit()
            except StaleDataError as error:
                session.rollback()
                actual_version = _profile_version(session, profile.profile_id)
                raise ConcurrencyConflict(
                    expected_version=profile.version,
                    actual_version=actual_version,
                ) from error

    def save_with_version(
        self, profile: SearchProfile, version: ProfileVersion
    ) -> None:
        with self.session_factory() as session:
            model = session.get(SearchProfileModel, profile.profile_id)
            if model is None:
                raise KeyError(profile.profile_id)
            if model.version != profile.version:
                raise ConcurrencyConflict(
                    expected_version=profile.version, actual_version=model.version
                )
            try:
                session.add(_version_model(version))
                session.flush()
                _update_profile_model(model, profile)
                session.commit()
            except (IntegrityError, StaleDataError) as error:
                session.rollback()
                actual_version = _profile_version(session, profile.profile_id)
                raise ConcurrencyConflict(
                    expected_version=profile.version,
                    actual_version=actual_version,
                ) from error


class SqlAlchemyProfileVersionRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert(self, version: ProfileVersion) -> None:
        with self.session_factory() as session:
            session.add(_version_model(version))
            session.commit()

    def get(self, version_id: UUID) -> ProfileVersion | None:
        with self.session_factory() as session:
            model = session.get(SearchProfileVersionModel, version_id)
            return _to_domain_version(model) if model is not None else None

    def latest_for_profile(self, profile_id: UUID) -> ProfileVersion | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(SearchProfileVersionModel)
                .where(SearchProfileVersionModel.profile_id == profile_id)
                .order_by(
                    SearchProfileVersionModel.profile_version.desc(),
                    SearchProfileVersionModel.created_at.desc(),
                )
                .limit(1)
            )
            return _to_domain_version(model) if model is not None else None


class SqlAlchemyRunRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert(self, run: RecommendationRun) -> None:
        with self.session_factory() as session:
            model = _run_model(run)
            session.add(model)
            session.commit()

    def reserve(self, run: RecommendationRun) -> RecommendationRun:
        with self.session_factory() as session:
            model = _run_model(run)
            session.add(model)
            try:
                session.commit()
            except IntegrityError as error:
                session.rollback()
                existing = _reserved_run(session, run)
                if existing is None:
                    raise ConcurrencyConflict(
                        expected_version=run.version,
                        actual_version=None,
                    ) from error
                return _to_domain_run(existing)
            return _to_domain_run(model)

    def bind_job(
        self, run_id: UUID, job_execution_id: UUID
    ) -> RecommendationRun:
        with self.session_factory() as session:
            model = session.get(RecommendationRunModel, run_id)
            if model is None:
                raise KeyError(run_id)
            if model.job_execution_id is not None:
                if model.job_execution_id == job_execution_id:
                    return _to_domain_run(model)
                raise ConcurrencyConflict(
                    expected_version=model.version,
                    actual_version=model.version,
                )
            expected_version = model.version
            model.job_execution_id = job_execution_id
            try:
                session.commit()
            except (IntegrityError, StaleDataError) as error:
                session.rollback()
                current = session.get(RecommendationRunModel, run_id)
                if (
                    current is not None
                    and current.job_execution_id == job_execution_id
                ):
                    return _to_domain_run(current)
                raise ConcurrencyConflict(
                    expected_version=expected_version,
                    actual_version=(current.version if current is not None else None),
                ) from error
            return _to_domain_run(model)

    def get(self, run_id: UUID) -> RecommendationRun | None:
        with self.session_factory() as session:
            model = session.get(RecommendationRunModel, run_id)
            return _to_domain_run(model) if model is not None else None

    def latest_for_profile(self, profile_id: UUID) -> RecommendationRun | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(RecommendationRunModel)
                .where(RecommendationRunModel.profile_id == profile_id)
                .order_by(RecommendationRunModel.created_at.desc())
                .limit(1)
            )
            return _to_domain_run(model) if model is not None else None

    def get_for_version(
        self, profile_id: UUID, profile_version_id: UUID
    ) -> RecommendationRun | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(RecommendationRunModel)
                .where(
                    RecommendationRunModel.profile_id == profile_id,
                    RecommendationRunModel.profile_version_id == profile_version_id,
                )
                .order_by(RecommendationRunModel.created_at.desc())
                .limit(1)
            )
            return _to_domain_run(model) if model is not None else None

    def get_reserved(
        self, profile_id: UUID, profile_version_id: UUID, trigger: str
    ) -> RecommendationRun | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(RecommendationRunModel).where(
                    RecommendationRunModel.profile_id == profile_id,
                    RecommendationRunModel.profile_version_id
                    == profile_version_id,
                    RecommendationRunModel.trigger == trigger,
                )
            )
            return _to_domain_run(model) if model is not None else None

    def latest_succeeded_for_profile(
        self, profile_id: UUID
    ) -> RecommendationRun | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(RecommendationRunModel)
                .where(
                    RecommendationRunModel.profile_id == profile_id,
                    RecommendationRunModel.state == "succeeded",
                )
                .order_by(RecommendationRunModel.created_at.desc())
                .limit(1)
            )
            return _to_domain_run(model) if model is not None else None

    def exists(self, profile_id: UUID, profile_version_id: UUID, trigger: str) -> bool:
        with self.session_factory() as session:
            row = session.scalar(
                select(RecommendationRunModel.id).where(
                    RecommendationRunModel.profile_id == profile_id,
                    RecommendationRunModel.profile_version_id == profile_version_id,
                    RecommendationRunModel.trigger == trigger,
                )
            )
            return row is not None

    def publish(
        self,
        run: RecommendationRun,
        items: tuple[RecommendationItem, ...],
        event: ProductEvent,
        evaluations: tuple[CriterionEvaluation, ...] = (),
    ) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            model = session.get(RecommendationRunModel, run.run_id)
            if model is None:
                raise KeyError(run.run_id)
            if model.version != run.version:
                raise ConcurrencyConflict(
                    expected_version=run.version, actual_version=model.version
                )
            model.state = "succeeded"
            model.candidate_count = run.candidate_count
            model.published_item_count = len(items)
            model.finished_at = run.finished_at or now
            model.updated_at = now
            for item in items:
                session.add(
                    RecommendationItemModel(
                        id=item.item_id,
                        created_at=now,
                        updated_at=now,
                        actor_kind="system",
                        actor_id=None,
                        source="radar.run",
                        correlation_id=run.correlation_id,
                        run_id=run.run_id,
                        listing_id=item.listing_id,
                        score=item.score,
                        position=item.position,
                        contributions=dict(item.contributions),
                    )
                )
            for evaluation in evaluations:
                session.add(
                    CriterionEvaluationModel(
                        id=evaluation.evaluation_id,
                        created_at=evaluation.created_at,
                        updated_at=evaluation.created_at,
                        actor_kind="system",
                        actor_id=None,
                        source="radar.run",
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
                )
            session.add(
                ProductEventRow(
                    id=event.event_id,
                    created_at=event.occurred_at,
                    updated_at=event.occurred_at,
                    actor_kind="system",
                    actor_id=str(event.actor_id)
                    if event.actor_id is not None
                    else None,
                    source="radar.run_publish",
                    correlation_id=event.correlation_id,
                    event_type=event.event_type,
                    event_version=event.event_version,
                    occurred_at=event.occurred_at,
                    payload=dict(event.payload),
                )
            )
            session.commit()

    def fail(self, run: RecommendationRun, failure_code: str) -> None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            model = session.get(RecommendationRunModel, run.run_id)
            if model is None:
                raise KeyError(run.run_id)
            if model.version != run.version:
                raise ConcurrencyConflict(
                    expected_version=run.version, actual_version=model.version
                )
            model.state = "failed"
            model.failure_code = failure_code
            model.finished_at = now
            model.updated_at = now
            session.commit()

    def supersede(
        self,
        run_id: UUID,
        *,
        reason: str,
        correlation_id: UUID,
    ) -> RecommendationRun | None:
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            model = session.get(RecommendationRunModel, run_id)
            if model is None:
                return None
            if model.state in {"succeeded", "failed", "superseded"}:
                return _to_domain_run(model)
            model.state = "superseded"
            model.failure_code = reason
            model.finished_at = now
            model.updated_at = now
            model.correlation_id = correlation_id
            session.commit()
            return _to_domain_run(model)

    def set_diagnostics(
        self,
        run_id: UUID,
        *,
        diagnostics: Mapping[str, object],
        correlation_id: UUID,
    ) -> RecommendationRun | None:
        with self.session_factory() as session:
            model = session.get(RecommendationRunModel, run_id)
            if model is None:
                return None
            model.diagnostics = dict(diagnostics)
            model.updated_at = datetime.now(timezone.utc)
            model.correlation_id = correlation_id
            session.commit()
            return _to_domain_run(model)


class SqlAlchemyItemRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def list_for_run(
        self, run_id: UUID, after_position: int | None, limit: int
    ) -> tuple[RecommendationItem, ...]:
        with self.session_factory() as session:
            statement = (
                select(RecommendationItemModel)
                .where(RecommendationItemModel.run_id == run_id)
                .order_by(
                    RecommendationItemModel.position.asc(),
                    RecommendationItemModel.id.asc(),
                )
                .limit(limit)
            )
            if after_position is not None:
                statement = statement.where(
                    RecommendationItemModel.position > after_position
                )
            models = session.scalars(statement)
            return tuple(_to_domain_item(model) for model in models)

    def listing_ids_for_run(self, run_id: UUID) -> tuple[UUID, ...]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(RecommendationItemModel.listing_id).where(
                    RecommendationItemModel.run_id == run_id
                )
            )
            return tuple(rows)

    def listing_accessible(self, owner_id: UUID, listing_id: UUID) -> bool:
        with self.session_factory() as session:
            row = session.scalar(
                select(RecommendationItemModel.id)
                .join(
                    RecommendationRunModel,
                    RecommendationRunModel.id == RecommendationItemModel.run_id,
                )
                .join(
                    SearchProfileModel,
                    SearchProfileModel.id == RecommendationRunModel.profile_id,
                )
                .where(
                    SearchProfileModel.owner_id == owner_id,
                    RecommendationRunModel.state == "succeeded",
                    RecommendationItemModel.listing_id == listing_id,
                )
                .limit(1)
            )
            return row is not None


class SqlAlchemyEventRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert(self, event: ProductEvent) -> None:
        with self.session_factory() as session:
            model = ProductEventRow(
                id=event.event_id,
                created_at=event.occurred_at,
                updated_at=event.occurred_at,
                actor_kind="service",
                actor_id=str(event.actor_id) if event.actor_id is not None else None,
                source="radar.events",
                correlation_id=event.correlation_id,
                event_type=event.event_type,
                event_version=event.event_version,
                occurred_at=event.occurred_at,
                payload=dict(event.payload),
            )
            session.add(model)
            session.commit()


class SqlAlchemyCandidateListingReader:
    """Narrows the silver listing set with the profile's hard bounds in SQL."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def list_candidates(
        self,
        profile: SearchProfile,
        *,
        supported_neighborhoods: tuple[str, ...],
        supported_property_types: tuple[str, ...],
    ) -> tuple[NormalizedListing, ...]:
        with self.session_factory() as session:
            statement = (
                select(
                    SilverListingModel,
                    func.ST_Y(cast(Any, SilverListingModel.geometry)).label("geo_lat"),
                    func.ST_X(cast(Any, SilverListingModel.geometry)).label("geo_lon"),
                )
                .where(
                    SilverListingModel.normalizer_version == ACTIVE_NORMALIZER_VERSION,
                    SilverListingModel.operation == profile.operation,
                    SilverListingModel.property_type.in_(
                        tuple(sorted(supported_property_types))
                    ),
                    func.lower(SilverListingModel.neighborhood).in_(
                        tuple(zone.casefold() for zone in supported_neighborhoods)
                    ),
                )
                .order_by(SilverListingModel.id)
            )
            if profile.budget_max is not None:
                statement = statement.where(
                    SilverListingModel.total_cost.is_not(None),
                    SilverListingModel.total_cost > 0,
                    SilverListingModel.total_cost <= profile.budget_max,
                )
            if profile.zones:
                zones = [zone.casefold() for zone in profile.zones]
                statement = statement.where(
                    func.lower(SilverListingModel.neighborhood).in_(zones)
                )
            if profile.min_rooms is not None and profile.min_rooms > 0:
                statement = statement.where(
                    (SilverListingModel.rooms.is_(None))
                    | (SilverListingModel.rooms >= profile.min_rooms)
                )
            rows = session.execute(statement).all()
            return tuple(_to_domain_listing(tuple(row)) for row in rows)


class SqlAlchemyListingReader:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def get(self, listing_id: UUID) -> NormalizedListing | None:
        with self.session_factory() as session:
            statement = select(
                SilverListingModel,
                func.ST_Y(cast(Any, SilverListingModel.geometry)).label("geo_lat"),
                func.ST_X(cast(Any, SilverListingModel.geometry)).label("geo_lon"),
            ).where(
                SilverListingModel.id == listing_id,
                SilverListingModel.normalizer_version == ACTIVE_NORMALIZER_VERSION,
            )
            row = session.execute(statement).first()
            return _to_domain_listing(tuple(row)) if row is not None else None

    def changes_for_listing(self, listing_id: UUID) -> tuple[Mapping[str, object], ...]:
        with self.session_factory() as session:
            models = session.scalars(
                select(ListingChangeModel)
                .where(ListingChangeModel.listing_id == listing_id)
                .order_by(ListingChangeModel.created_at)
            )
            return tuple(
                {
                    "change_type": model.change_type,
                    "field": model.field,
                    "before": model.before,
                    "after": model.after,
                }
                for model in models
            )


def _profile_model(profile: SearchProfile) -> SearchProfileModel:
    return SearchProfileModel(
        id=profile.profile_id,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        actor_kind=profile.actor_kind,
        actor_id=profile.actor_id,
        source="radar.profile",
        correlation_id=profile.correlation_id,
        owner_id=profile.owner_id,
        name=profile.name,
        operation=profile.operation,
        zones=list(profile.zones),
        budget_max=profile.budget_max,
        budget_min=profile.budget_min,
        min_rooms=profile.min_rooms,
        surface_min=profile.surface_min,
        surface_max=profile.surface_max,
        status=profile.status,
        unknown_strategy=dict(profile.unknown_strategy),
        current_version_id=profile.current_version_id,
        latest_run_id=profile.latest_run_id,
    )


def _update_profile_model(
    model: SearchProfileModel, profile: SearchProfile
) -> None:
    model.name = profile.name
    model.zones = list(profile.zones)
    model.budget_max = cast(Any, profile.budget_max)
    model.budget_min = profile.budget_min
    model.min_rooms = cast(Any, profile.min_rooms)
    model.surface_min = profile.surface_min
    model.surface_max = profile.surface_max
    model.status = profile.status
    model.unknown_strategy = dict(profile.unknown_strategy)
    model.current_version_id = profile.current_version_id
    model.latest_run_id = profile.latest_run_id
    model.updated_at = profile.updated_at


def _version_model(version: ProfileVersion) -> SearchProfileVersionModel:
    return SearchProfileVersionModel(
        id=version.version_id,
        created_at=version.created_at,
        updated_at=version.created_at,
        actor_kind=version.actor_kind,
        actor_id=version.actor_id,
        source="radar.profile",
        correlation_id=version.correlation_id,
        profile_id=version.profile_id,
        profile_version=version.profile_version,
        payload=dict(version.payload),
    )


def _profile_version(session: Session, profile_id: UUID) -> int | None:
    model = session.get(SearchProfileModel, profile_id)
    return model.version if model is not None else None


def _reserved_run(
    session: Session, run: RecommendationRun
) -> RecommendationRunModel | None:
    return session.scalar(
        select(RecommendationRunModel).where(
            RecommendationRunModel.profile_id == run.profile_id,
            RecommendationRunModel.profile_version_id == run.profile_version_id,
            RecommendationRunModel.trigger == run.trigger,
        )
    )


def _run_model(run: RecommendationRun) -> RecommendationRunModel:
    return RecommendationRunModel(
        id=run.run_id,
        created_at=run.created_at,
        updated_at=run.created_at,
        actor_kind=run.actor_kind,
        actor_id=run.actor_id,
        source="radar.run",
        correlation_id=run.correlation_id,
        profile_id=run.profile_id,
        profile_version_id=run.profile_version_id,
        state=run.state,
        trigger=run.trigger,
        score_policy_version=run.score_policy_version,
        candidate_count=run.candidate_count,
        published_item_count=run.published_item_count,
        failure_code=run.failure_code,
        job_execution_id=run.job_execution_id,
        finished_at=run.finished_at,
        diagnostics=dict(run.diagnostics or {}),
    )


def _to_domain_profile(model: SearchProfileModel) -> SearchProfile:
    return SearchProfile(
        profile_id=model.id,
        owner_id=model.owner_id,
        name=model.name,
        operation=cast(Any, model.operation),
        zones=tuple(model.zones or ()),
        budget_max=float(model.budget_max) if model.budget_max is not None else None,
        budget_min=float(model.budget_min) if model.budget_min is not None else None,
        min_rooms=model.min_rooms,
        surface_min=(
            float(model.surface_min) if model.surface_min is not None else None
        ),
        surface_max=(
            float(model.surface_max) if model.surface_max is not None else None
        ),
        status=cast(SearchProfileState, model.status),
        unknown_strategy=dict(model.unknown_strategy or {}),
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        current_version_id=model.current_version_id,
        latest_run_id=model.latest_run_id,
        correlation_id=model.correlation_id,
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
    )


def _to_domain_version(model: SearchProfileVersionModel) -> ProfileVersion:
    return ProfileVersion(
        version_id=model.id,
        profile_id=model.profile_id,
        profile_version=model.profile_version,
        payload=dict(model.payload or {}),
        created_at=model.created_at,
        correlation_id=model.correlation_id,
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
    )


def _to_domain_run(model: RecommendationRunModel) -> RecommendationRun:
    return RecommendationRun(
        run_id=model.id,
        profile_id=model.profile_id,
        profile_version_id=model.profile_version_id,
        state=cast(Any, model.state),
        trigger=cast(Any, model.trigger),
        score_policy_version=model.score_policy_version,
        candidate_count=model.candidate_count,
        published_item_count=model.published_item_count,
        failure_code=model.failure_code,
        job_execution_id=model.job_execution_id,
        created_at=model.created_at,
        finished_at=model.finished_at,
        correlation_id=model.correlation_id,
        version=model.version,
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
        diagnostics=dict(model.diagnostics or {}),
    )


def _to_domain_item(model: RecommendationItemModel) -> RecommendationItem:
    return RecommendationItem(
        item_id=model.id,
        run_id=model.run_id,
        listing_id=model.listing_id,
        score=float(model.score),
        position=model.position,
        contributions=dict(model.contributions or {}),
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
        operation=cast(Any, model.operation),
        property_type=cast(Any, model.property_type),
        price_value=float(model.price_value),
        price_currency=cast(Any, model.price_currency),
        expenses_value=(
            float(model.expenses_value) if model.expenses_value is not None else None
        ),
        expenses_currency=cast(Any, model.expenses_currency),
        total_cost=float(model.total_cost),
        price_assumptions=dict(model.price_assumptions or {}),
        title_text=model.title_text,
        surface_m2=float(model.surface_m2) if model.surface_m2 is not None else None,
        surface_covered_m2=(
            float(model.surface_covered_m2)
            if model.surface_covered_m2 is not None
            else None
        ),
        rooms=model.rooms,
        bedrooms=model.bedrooms,
        bathrooms=(float(model.bathrooms) if model.bathrooms is not None else None),
        toilettes=(float(model.toilettes) if model.toilettes is not None else None),
        parking_spaces=(
            float(model.parking_spaces) if model.parking_spaces is not None else None
        ),
        floor=model.floor,
        age_years=(float(model.age_years) if model.age_years is not None else None),
        disposition=model.disposition,
        orientation=model.orientation,
        amenities=tuple(model.amenities or ()),
        description_text=model.description_text,
        media_urls=tuple(model.media_urls or ()),
        location_text=model.location_text,
        neighborhood=model.neighborhood,
        geo_precision=cast(GeoPrecision, model.geo_precision),
        geometry=geometry,
        geo_source=model.geo_source,
        normalization_errors=tuple(model.normalization_errors or ()),
    )
