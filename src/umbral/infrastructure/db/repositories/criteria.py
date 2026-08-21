"""SQLAlchemy repositories for the criteria and observations domain.

Each method owns its commit, mirroring the radar repositories. The atomic
``ObservationRepository.publish`` commits new observations + superseded rows +
recompute run state + batch/recompute event in one transaction; partial unique
indexes arbitrate interrupted retries.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.orm import Session

from umbral.application.criteria.contracts import (
    Compilation,
    Concept,
    ConceptVersion,
    ExtractionVersion,
    ListingObservation,
    PreferenceFact,
    RecomputeRun,
    RecomputeScope,
)
from umbral.application.events.contracts import ProductEvent
from umbral.application.silver.contracts import NormalizedListing
from umbral.infrastructure.db.models.criteria import (
    Concept as ConceptModel,
)
from umbral.infrastructure.db.models.criteria import (
    ConceptVersion as ConceptVersionModel,
)
from umbral.infrastructure.db.models.criteria import (
    ExtractionVersion as ExtractionVersionModel,
)
from umbral.infrastructure.db.models.criteria import (
    ListingEmbedding as ListingEmbeddingModel,
)
from umbral.infrastructure.db.models.criteria import (
    ListingObservation as ListingObservationModel,
)
from umbral.infrastructure.db.models.criteria import (
    PreferenceFact as PreferenceFactModel,
)
from umbral.infrastructure.db.models.criteria import (
    ProfileCriteriaCompilation as CompilationModel,
)
from umbral.infrastructure.db.models.criteria import (
    RecomputeRun as RecomputeRunModel,
)
from umbral.infrastructure.db.models.radar import ProductEventRow
from umbral.infrastructure.db.models.silver import (
    SilverListing as SilverListingModel,
)

SessionFactory = Callable[[], Session]


def _to_domain_concept(model: ConceptModel) -> Concept:
    return Concept(
        concept_id=model.id,
        key=model.key,
        name=model.name,
        aliases=tuple(model.aliases or []),
        matcher_type=model.matcher_type,  # type: ignore[arg-type]
        params_schema=dict(model.params_schema or {}),
        source=model.source,
        defaults=dict(model.defaults or {}),
        compute_policy=dict(model.compute_policy or {}),
        version=model.version,
        current_version_id=model.current_version_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
        correlation_id=model.correlation_id,
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
    )


def _to_domain_concept_version(model: ConceptVersionModel) -> ConceptVersion:
    return ConceptVersion(
        version_id=model.id,
        concept_id=model.concept_id,
        concept_version=model.concept_version,
        payload=dict(model.payload or {}),
        created_at=model.created_at,
        correlation_id=model.correlation_id,
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
    )


class SqlAlchemyConceptRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert(self, concept: Concept) -> None:
        with self.session_factory() as session:
            session.add(_concept_model(concept))
            session.commit()

    def save(self, concept: Concept) -> None:
        with self.session_factory() as session:
            model = session.get(ConceptModel, concept.concept_id)
            if model is None:
                raise KeyError(concept.concept_id)
            model.name = concept.name
            model.aliases = list(concept.aliases)
            model.matcher_type = concept.matcher_type
            model.params_schema = dict(concept.params_schema)
            model.defaults = dict(concept.defaults)
            model.compute_policy = dict(concept.compute_policy)
            model.current_version_id = concept.current_version_id
            model.updated_at = concept.updated_at
            session.commit()

    def get(self, key: str) -> Concept | None:
        with self.session_factory() as session:
            model = session.scalar(select(ConceptModel).where(ConceptModel.key == key))
            return _to_domain_concept(model) if model is not None else None

    def list_active(self) -> tuple[Concept, ...]:
        with self.session_factory() as session:
            models = session.scalars(select(ConceptModel).order_by(ConceptModel.key))
            return tuple(_to_domain_concept(model) for model in models)

    def insert_version(self, version: ConceptVersion) -> None:
        with self.session_factory() as session:
            session.add(
                ConceptVersionModel(
                    id=version.version_id,
                    created_at=version.created_at,
                    updated_at=version.created_at,
                    actor_kind=version.actor_kind,
                    actor_id=version.actor_id,
                    source="criteria.concept",
                    correlation_id=version.correlation_id,
                    concept_id=version.concept_id,
                    concept_version=version.concept_version,
                    payload=dict(version.payload),
                )
            )
            session.commit()

    def latest_version(self, concept_id: UUID) -> ConceptVersion | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(ConceptVersionModel)
                .where(ConceptVersionModel.concept_id == concept_id)
                .order_by(ConceptVersionModel.concept_version.desc())
                .limit(1)
            )
            return _to_domain_concept_version(model) if model is not None else None


class SqlAlchemyFactRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def record_change(self, fact: PreferenceFact, superseded_by: UUID | None) -> None:
        with self.session_factory() as session:
            if superseded_by is not None:
                session.execute(
                    update(PreferenceFactModel)
                    .where(
                        PreferenceFactModel.profile_id == fact.profile_id,
                        PreferenceFactModel.concept_key == fact.concept_key,
                        PreferenceFactModel.state == "active",
                    )
                    .values(state="superseded", superseded_by=superseded_by)
                )
            session.add(
                PreferenceFactModel(
                    id=fact.fact_id,
                    created_at=fact.created_at,
                    updated_at=fact.created_at,
                    actor_kind=fact.actor_kind,
                    actor_id=fact.actor_id,
                    source="criteria.fact",
                    correlation_id=fact.correlation_id,
                    profile_id=fact.profile_id,
                    concept_key=fact.concept_key,
                    value=fact.value,
                    weight=fact.weight,
                    polarity=fact.polarity,
                    confidence=fact.confidence,
                    fact_source=fact.fact_source,
                    state=fact.state,
                    superseded_by=fact.superseded_by,
                )
            )
            session.commit()

    def active_for_profile(self, profile_id: UUID) -> tuple[PreferenceFact, ...]:
        with self.session_factory() as session:
            models = session.scalars(
                select(PreferenceFactModel).where(
                    PreferenceFactModel.profile_id == profile_id,
                    PreferenceFactModel.state == "active",
                )
            )
            return tuple(_to_domain_fact(model) for model in models)

    def supersede_active(
        self,
        profile_id: UUID,
        concept_key: str,
        *,
        superseded_by: UUID | None,
        correlation_id: UUID,
        actor_kind: str,
        actor_id: str | None,
    ) -> int:
        with self.session_factory() as session:
            now = datetime.now(timezone.utc)
            result = session.execute(
                update(PreferenceFactModel)
                .where(
                    PreferenceFactModel.profile_id == profile_id,
                    PreferenceFactModel.concept_key == concept_key,
                    PreferenceFactModel.state == "active",
                )
                .values(
                    state="superseded",
                    superseded_by=superseded_by,
                    updated_at=now,
                    actor_kind=actor_kind,
                    actor_id=actor_id,
                    correlation_id=correlation_id,
                )
            )
            session.commit()
            return int(cast(CursorResult[Any], result).rowcount or 0)


class SqlAlchemyCompilationRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert(self, compilation: Compilation) -> None:
        with self.session_factory() as session:
            session.add(
                CompilationModel(
                    id=compilation.compilation_id,
                    created_at=compilation.created_at,
                    updated_at=compilation.created_at,
                    actor_kind=compilation.actor_kind,
                    actor_id=compilation.actor_id,
                    source="criteria.compilation",
                    correlation_id=compilation.correlation_id,
                    profile_id=compilation.profile_id,
                    profile_version_id=compilation.profile_version_id,
                    compilation_version=compilation.compilation_version,
                    criteria=[_criterion_payload(c) for c in compilation.criteria],
                    warnings=list(compilation.warnings),
                    confirmations=list(compilation.confirmations),
                )
            )
            session.commit()

    def latest_for_profile_version(
        self, profile_version_id: UUID
    ) -> Compilation | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(CompilationModel)
                .where(CompilationModel.profile_version_id == profile_version_id)
                .order_by(CompilationModel.compilation_version.desc())
                .limit(1)
            )
            return _to_domain_compilation(model) if model is not None else None


class SqlAlchemyExtractionVersionRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert(self, version: ExtractionVersion) -> None:
        with self.session_factory() as session:
            session.add(
                ExtractionVersionModel(
                    id=version.version_id,
                    created_at=version.created_at,
                    updated_at=version.created_at,
                    actor_kind=version.actor_kind,
                    actor_id=version.actor_id,
                    source="criteria.extraction",
                    correlation_id=version.correlation_id,
                    kind=version.kind,
                    key=version.key,
                    artifact_version=version.version,
                    payload=dict(version.payload),
                )
            )
            session.commit()

    def get(self, version_id: UUID) -> ExtractionVersion | None:
        with self.session_factory() as session:
            model = session.get(ExtractionVersionModel, version_id)
            return _to_domain_extraction_version(model) if model is not None else None

    def find(self, kind: str, key: str, version: str) -> ExtractionVersion | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(ExtractionVersionModel).where(
                    ExtractionVersionModel.kind == kind,
                    ExtractionVersionModel.key == key,
                    ExtractionVersionModel.artifact_version == version,
                )
            )
            return _to_domain_extraction_version(model) if model is not None else None

    def latest(self, kind: str, key: str) -> ExtractionVersion | None:
        with self.session_factory() as session:
            model = session.scalar(
                select(ExtractionVersionModel)
                .where(
                    ExtractionVersionModel.kind == kind,
                    ExtractionVersionModel.key == key,
                )
                .order_by(ExtractionVersionModel.created_at.desc())
                .limit(1)
            )
            return _to_domain_extraction_version(model) if model is not None else None


class SqlAlchemyObservationRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def invalidate_for_concept(self, concept_key: str) -> int:
        with self.session_factory() as session:
            result = session.execute(
                update(ListingObservationModel)
                .where(
                    ListingObservationModel.concept_key == concept_key,
                    ListingObservationModel.state == "active",
                )
                .values(state="invalidated")
            )
            session.commit()
            return int(cast(CursorResult[Any], result).rowcount or 0)

    def invalidate_active_for_source(self, source: str) -> int:
        """Invalidate active observations of a source so they can be re-published."""
        with self.session_factory() as session:
            result = session.execute(
                update(ListingObservationModel)
                .where(
                    ListingObservationModel.source == source,
                    ListingObservationModel.state == "active",
                )
                .values(state="invalidated")
            )
            session.commit()
            return int(cast(CursorResult[Any], result).rowcount or 0)

    def invalidate_for_extraction_version(self, extraction_version_id: UUID) -> int:
        with self.session_factory() as session:
            result = session.execute(
                update(ListingObservationModel)
                .where(
                    ListingObservationModel.extraction_version_id
                    == extraction_version_id,
                    ListingObservationModel.state == "active",
                )
                .values(state="invalidated")
            )
            session.commit()
            return int(cast(CursorResult[Any], result).rowcount or 0)

    def invalidate_for_normalizer_version(self, normalizer_version: str) -> int:
        with self.session_factory() as session:
            result = session.execute(
                update(ListingObservationModel)
                .where(
                    ListingObservationModel.listing_id.in_(
                        select(SilverListingModel.id).where(
                            SilverListingModel.normalizer_version == normalizer_version
                        )
                    ),
                    ListingObservationModel.state == "active",
                )
                .values(state="invalidated")
            )
            session.commit()
            return int(cast(CursorResult[Any], result).rowcount or 0)

    def ids_for_scope(self, scope: RecomputeScope) -> tuple[UUID, ...]:
        with self.session_factory() as session:
            statement = select(ListingObservationModel.id).where(
                ListingObservationModel.state.in_(("active", "invalidated"))
            )
            if scope.kind == "concept" and scope.key:
                statement = statement.where(
                    ListingObservationModel.concept_key == scope.key
                )
            elif scope.kind == "extraction" and scope.key:
                statement = statement.where(
                    ListingObservationModel.extraction_version_id == UUID(scope.key)
                )
            elif scope.kind == "parser" and scope.key:
                statement = statement.where(
                    ListingObservationModel.listing_id.in_(
                        select(SilverListingModel.id).where(
                            SilverListingModel.normalizer_version == scope.key
                        )
                    )
                )
            return tuple(session.scalars(statement))

    def publish(
        self,
        observations: tuple[ListingObservation, ...],
        supersede_ids: tuple[UUID, ...],
        run: RecomputeRun | None,
        event: ProductEvent | None,
    ) -> None:
        with self.session_factory() as session:
            if supersede_ids:
                session.execute(
                    update(ListingObservationModel)
                    .where(ListingObservationModel.id.in_(supersede_ids))
                    .values(state="superseded")
                )
            for observation in observations:
                session.add(_observation_model(observation))
            if run is not None:
                model = session.get(RecomputeRunModel, run.run_id)
                if model is None:
                    raise KeyError(run.run_id)
                model.state = run.state
                model.counts = dict(run.counts)
                model.finished_at = run.finished_at
                model.updated_at = run.finished_at or datetime.now(timezone.utc)
            if event is not None:
                session.add(
                    ProductEventRow(
                        id=event.event_id,
                        created_at=event.occurred_at,
                        updated_at=event.occurred_at,
                        actor_kind="service",
                        actor_id=str(event.actor_id) if event.actor_id else None,
                        source="criteria.observation",
                        correlation_id=event.correlation_id,
                        event_type=event.event_type,
                        event_version=event.event_version,
                        occurred_at=event.occurred_at,
                        payload=dict(event.payload),
                    )
                )
            session.commit()


class SqlAlchemyRecomputeRunRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def insert(self, run: RecomputeRun) -> None:
        with self.session_factory() as session:
            session.add(
                RecomputeRunModel(
                    id=run.run_id,
                    created_at=run.created_at,
                    updated_at=run.created_at,
                    actor_kind=run.actor_kind,
                    actor_id=run.actor_id,
                    source="criteria.recompute",
                    correlation_id=run.correlation_id,
                    scope_kind=run.scope.kind,
                    scope_key=run.scope.key,
                    cause=run.cause,
                    state=run.state,
                    counts=dict(run.counts),
                    job_execution_id=run.job_execution_id,
                    finished_at=run.finished_at,
                )
            )
            session.commit()

    def get(self, run_id: UUID) -> RecomputeRun | None:
        with self.session_factory() as session:
            model = session.get(RecomputeRunModel, run_id)
            return _to_domain_recompute_run(model) if model is not None else None

    def fail(self, run: RecomputeRun, failure_code: str) -> None:
        with self.session_factory() as session:
            model = session.get(RecomputeRunModel, run.run_id)
            if model is None:
                raise KeyError(run.run_id)
            model.state = "failed"
            model.counts = dict(run.counts)
            model.finished_at = run.finished_at
            model.updated_at = run.finished_at or datetime.now(timezone.utc)
            session.commit()


class SqlAlchemyEmbeddingRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def publish_embeddings(
        self,
        listing_ids: tuple[UUID, ...],
        extraction_version_id: UUID,
        vectors: Mapping[UUID, tuple[float, ...]],
        run: RecomputeRun | None,
    ) -> None:
        with self.session_factory() as session:
            for listing_id in listing_ids:
                session.execute(
                    update(ListingEmbeddingModel)
                    .where(
                        ListingEmbeddingModel.listing_id == listing_id,
                        ListingEmbeddingModel.extraction_version_id
                        == extraction_version_id,
                        ListingEmbeddingModel.state == "active",
                    )
                    .values(state="superseded")
                )
                vector = vectors.get(listing_id)
                if vector is not None:
                    session.add(
                        ListingEmbeddingModel(
                            id=uuid4(),
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc),
                            actor_kind="service",
                            source="criteria.embedding",
                            correlation_id=uuid4(),
                            listing_id=listing_id,
                            extraction_version_id=extraction_version_id,
                            embedding=list(vector),
                            state="active",
                            recomputation_run_id=run.run_id if run else None,
                        )
                    )
            session.commit()

    def active_versions_for_listing(self, listing_id: UUID) -> tuple[UUID, ...]:
        with self.session_factory() as session:
            models = session.scalars(
                select(ListingEmbeddingModel).where(
                    ListingEmbeddingModel.listing_id == listing_id,
                    ListingEmbeddingModel.state == "active",
                )
            )
            return tuple(model.extraction_version_id for model in models)


class SqlAlchemyCriteriaListingReader:
    """Reads Silver listings as projections for extraction batches."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def _select(self) -> Any:
        return select(
            SilverListingModel,
            func.ST_Y(SilverListingModel.geometry).label("geo_lat"),
            func.ST_X(SilverListingModel.geometry).label("geo_lon"),
        )

    def _price_changes(
        self, session: Session, listing_ids: tuple[UUID, ...]
    ) -> dict[UUID, tuple[Mapping[str, object], ...]]:
        from umbral.infrastructure.db.models.silver import ListingChange

        if not listing_ids:
            return {}
        models = session.scalars(
            select(ListingChange)
            .where(
                ListingChange.listing_id.in_(listing_ids),
                ListingChange.change_type == "price",
            )
            .order_by(ListingChange.created_at.desc())
        )
        grouped: dict[UUID, list[Mapping[str, object]]] = {}
        for model in models:
            grouped.setdefault(model.listing_id, []).append(
                {
                    "field": model.field,
                    "before": model.before,
                    "after": model.after,
                }
            )
        return {
            listing_id: tuple(entries)
            for listing_id, entries in grouped.items()
        }

    def _hydrate(
        self, session: Session, rows: Sequence[Any]
    ) -> tuple[NormalizedListing, ...]:
        from dataclasses import replace

        listings = tuple(_to_domain_listing(tuple(row)) for row in rows)
        if not listings:
            return ()
        price_changes = self._price_changes(
            session, tuple(item.listing_id for item in listings)
        )
        return tuple(
            replace(item, price_changes=price_changes.get(item.listing_id, ()))
            if price_changes.get(item.listing_id)
            else item
            for item in listings
        )

    def get(self, listing_id: UUID) -> NormalizedListing | None:
        with self.session_factory() as session:
            row = session.execute(
                self._select().where(SilverListingModel.id == listing_id)
            ).first()
            if row is None:
                return None
            listings = self._hydrate(session, (row,))
            return listings[0] if listings else None

    def list_all(self) -> tuple[NormalizedListing, ...]:
        with self.session_factory() as session:
            rows = session.execute(self._select().order_by(SilverListingModel.id))
            return self._hydrate(session, rows.all())

    def list_by_normalizer_version(
        self, normalizer_version: str
    ) -> tuple[NormalizedListing, ...]:
        with self.session_factory() as session:
            rows = session.execute(
                self._select().where(
                    SilverListingModel.normalizer_version == normalizer_version
                )
            )
            return self._hydrate(session, rows.all())


class SqlAlchemyProfileSnapshotReader:
    """Reads search profile versions and owners for criteria compilation."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def get_payload(self, profile_version_id: UUID) -> Mapping[str, object] | None:
        from umbral.infrastructure.db.models.radar import SearchProfileVersion

        with self.session_factory() as session:
            model = session.get(SearchProfileVersion, profile_version_id)
            return dict(model.payload) if model is not None else None

    def get_version(self, profile_version_id: UUID) -> tuple[UUID, int] | None:
        from umbral.infrastructure.db.models.radar import SearchProfileVersion

        with self.session_factory() as session:
            model = session.get(SearchProfileVersion, profile_version_id)
            return (
                (model.profile_id, model.profile_version) if model is not None else None
            )

    def owner_of(self, profile_id: UUID) -> UUID | None:
        from umbral.infrastructure.db.models.radar import SearchProfile

        with self.session_factory() as session:
            model = session.get(SearchProfile, profile_id)
            return model.owner_id if model is not None else None


def _to_domain_fact(model: PreferenceFactModel) -> PreferenceFact:
    return PreferenceFact(
        fact_id=model.id,
        profile_id=model.profile_id,
        concept_key=model.concept_key,
        value=model.value,
        weight=float(model.weight),
        polarity=model.polarity,
        confidence=float(model.confidence),
        fact_source=model.fact_source,
        state=model.state,  # type: ignore[arg-type]
        superseded_by=model.superseded_by,
        created_at=model.created_at,
        correlation_id=model.correlation_id,
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
        soft_to_hard=bool(model.soft_to_hard),
    )


def _to_domain_compilation(model: CompilationModel) -> Compilation:
    from umbral.application.criteria.contracts import CompiledCriterion

    criteria = tuple(
        CompiledCriterion(
            concept_key=str(item["concept_key"]),
            matcher_type=str(item["matcher_type"]),  # type: ignore[arg-type]
            params=_criterion_params(item),
            source_ref=str(item.get("source_ref", "")),
            soft_to_hard=bool(item.get("soft_to_hard", False)),
            weight=_as_optional_float(item.get("weight")),
        )
        for item in (model.criteria or [])
    )
    return Compilation(
        compilation_id=model.id,
        profile_id=model.profile_id,
        profile_version_id=model.profile_version_id,
        compilation_version=model.compilation_version,
        criteria=criteria,
        warnings=tuple(model.warnings or []),
        confirmations=tuple(model.confirmations or []),
        created_at=model.created_at,
        correlation_id=model.correlation_id,
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
    )


def _criterion_payload(criterion: object) -> dict[str, object]:
    from umbral.application.criteria.contracts import CompiledCriterion

    item = criterion
    assert isinstance(item, CompiledCriterion)
    payload: dict[str, object] = {
        "concept_key": item.concept_key,
        "matcher_type": item.matcher_type,
        "params": dict(item.params),
        "source_ref": item.source_ref,
        "soft_to_hard": item.soft_to_hard,
    }
    if item.weight is not None:
        payload["weight"] = item.weight
    return payload


def _to_domain_extraction_version(
    model: ExtractionVersionModel,
) -> ExtractionVersion:
    return ExtractionVersion(
        version_id=model.id,
        kind=model.kind,  # type: ignore[arg-type]
        key=model.key,
        version=model.artifact_version,
        payload=dict(model.payload or {}),
        created_at=model.created_at,
        correlation_id=model.correlation_id,
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
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
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
    )


def _observation_model(observation: ListingObservation) -> ListingObservationModel:
    return ListingObservationModel(
        id=observation.observation_id,
        created_at=observation.created_at,
        updated_at=observation.created_at,
        actor_kind=observation.actor_kind,
        actor_id=observation.actor_id,
        correlation_id=observation.correlation_id,
        listing_id=observation.listing_id,
        concept_key=observation.concept_key,
        matcher_type=observation.matcher_type,
        value=observation.value,
        score=observation.score,
        confidence=observation.confidence,
        evidence=dict(observation.evidence),
        source=observation.source,
        extraction_version_id=observation.extraction_version_id,
        state=observation.state,
        failure_code=observation.failure_code,
        recomputation_run_id=observation.recomputation_run_id,
    )


def _to_domain_recompute_run(model: RecomputeRunModel) -> RecomputeRun:
    from umbral.application.criteria.contracts import RecomputeScope

    return RecomputeRun(
        run_id=model.id,
        scope=RecomputeScope(model.scope_kind, model.scope_key),  # type: ignore[arg-type]
        cause=model.cause,
        state=model.state,  # type: ignore[arg-type]
        counts=dict(model.counts or {}),
        job_execution_id=model.job_execution_id,
        finished_at=model.finished_at,
        created_at=model.created_at,
        correlation_id=model.correlation_id,
        version=model.version,
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
    )


def _to_domain_listing(row: tuple[object, ...]) -> NormalizedListing:
    from umbral.application.ingestion.contracts import SourceIdentity

    model = row[0]
    assert isinstance(model, SilverListingModel)
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
        geo_precision=model.geo_precision,  # type: ignore[arg-type]
        geometry=geometry,
        geo_source=model.geo_source,
        normalization_errors=tuple(model.normalization_errors or []),
    )


def _concept_model(concept: Concept) -> ConceptModel:
    return ConceptModel(
        id=concept.concept_id,
        created_at=concept.created_at,
        updated_at=concept.updated_at,
        actor_kind=concept.actor_kind,
        actor_id=concept.actor_id,
        source="criteria.concept",
        correlation_id=concept.correlation_id,
        key=concept.key,
        name=concept.name,
        aliases=list(concept.aliases),
        matcher_type=concept.matcher_type,
        params_schema=dict(concept.params_schema),
        defaults=dict(concept.defaults),
        compute_policy=dict(concept.compute_policy),
        current_version_id=concept.current_version_id,
    )


def _as_mapping_signal(signal: Mapping[str, object]) -> dict[str, object]:
    payload = signal.get("payload")
    return dict(payload) if isinstance(payload, Mapping) else {}


def _criterion_params(item: Mapping[str, object]) -> dict[str, object]:
    params = item.get("params")
    return dict(params) if isinstance(params, Mapping) else {}


def _as_optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
