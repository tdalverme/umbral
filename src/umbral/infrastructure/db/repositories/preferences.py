"""SQLAlchemy adapters for the deep preference mutation seam."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from umbral.application.criteria.contracts import MatcherType
from umbral.application.preferences.contracts import (
    BindingKind,
    BindingMode,
    BindingStatus,
    CriterionBinding,
    PreferenceAuthority,
    PreferenceExpression,
    PreferenceMutation,
    PreferenceMutationResult,
    PreferenceSourceKind,
    PreferenceStatus,
)
from umbral.infrastructure.db.models.criteria import PreferenceFact
from umbral.infrastructure.db.models.preferences import (
    CriterionBinding as CriterionBindingModel,
)
from umbral.infrastructure.db.models.preferences import (
    PreferenceExpression as PreferenceExpressionModel,
)
from umbral.infrastructure.db.models.radar import SearchProfile, SearchProfileVersion

SessionFactory = Callable[[], Session]


class SqlAlchemyExpressionRepository:
    """Read expressions and commit each complete preference mutation atomically."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def get(self, expression_id: UUID) -> PreferenceExpression | None:
        with self.session_factory() as session:
            model = session.get(PreferenceExpressionModel, expression_id)
            return _to_expression(model) if model is not None else None

    def active_for_profile(
        self, profile_id: UUID
    ) -> tuple[PreferenceExpression, ...]:
        with self.session_factory() as session:
            models = session.scalars(
                select(PreferenceExpressionModel)
                .where(
                    PreferenceExpressionModel.profile_id == profile_id,
                    PreferenceExpressionModel.status == "active",
                )
                .order_by(
                    PreferenceExpressionModel.created_at,
                    PreferenceExpressionModel.id,
                )
            )
            return tuple(_to_expression(model) for model in models)

    def apply(self, mutation: PreferenceMutation) -> PreferenceMutationResult:
        """Apply expression, binding, fact and retirement changes in one commit."""

        with self.session_factory() as session:
            try:
                predecessor, retired_bindings = _lock_mutation_rows(session, mutation)
                new_fact_ids = {
                    binding_id: uuid4() for binding_id in mutation.fact_binding_ids
                }
                _retire_facts(
                    retired_bindings,
                    mutation,
                    new_fact_ids,
                    session,
                )
                if mutation.kind != "withdraw":
                    session.add(_expression_model(mutation.expression))
                    session.flush()
                    session.add_all(
                        _binding_model(binding) for binding in mutation.bindings
                    )
                    session.flush()
                _retire_predecessor(
                    predecessor,
                    retired_bindings,
                    mutation,
                )
                if mutation.kind != "withdraw":
                    session.add_all(
                        _fact_model(
                            mutation,
                            binding,
                            fact_id=new_fact_ids[binding.binding_id],
                        )
                        for binding in mutation.bindings
                        if binding.binding_id in new_fact_ids
                    )
                session.commit()
                return PreferenceMutationResult(
                    fact_ids=tuple(
                        new_fact_ids[binding_id]
                        for binding_id in mutation.fact_binding_ids
                    )
                )
            except Exception:
                session.rollback()
                raise


class SqlAlchemyBindingRepository:
    """Read safe binding views and explicitly load semantic vectors for scoring."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def active_for_expression_ids(
        self, expression_ids: tuple[UUID, ...]
    ) -> tuple[CriterionBinding, ...]:
        if not expression_ids:
            return ()
        with self.session_factory() as session:
            models = session.scalars(
                select(CriterionBindingModel)
                .where(
                    CriterionBindingModel.expression_id.in_(expression_ids),
                    CriterionBindingModel.status == "active",
                )
                .order_by(
                    CriterionBindingModel.created_at,
                    CriterionBindingModel.id,
                )
            )
            return tuple(_to_binding(model) for model in models)

    def active_semantic_for_profile_version(
        self, profile_version_id: UUID
    ) -> tuple[CriterionBinding, ...]:
        """Load private query vectors only for current semantic scoring inputs."""

        with self.session_factory() as session:
            models = session.scalars(
                select(CriterionBindingModel)
                .join(
                    PreferenceExpressionModel,
                    PreferenceExpressionModel.id
                    == CriterionBindingModel.expression_id,
                )
                .join(
                    SearchProfileVersion,
                    SearchProfileVersion.profile_id
                    == PreferenceExpressionModel.profile_id,
                )
                .where(
                    SearchProfileVersion.id == profile_version_id,
                    PreferenceExpressionModel.status == "active",
                    CriterionBindingModel.status == "active",
                    CriterionBindingModel.kind == "semantic",
                    CriterionBindingModel.query_embedding.is_not(None),
                    CriterionBindingModel.embedding_version_id.is_not(None),
                )
                .order_by(CriterionBindingModel.id)
            )
            return tuple(_to_binding(model) for model in models)


def _lock_mutation_rows(
    session: Session,
    mutation: PreferenceMutation,
) -> tuple[PreferenceExpressionModel | None, tuple[CriterionBindingModel, ...]]:
    profile_id = session.scalar(
        select(SearchProfile.id)
        .where(SearchProfile.id == mutation.expression.profile_id)
        .with_for_update()
    )
    if profile_id is None:
        raise RuntimeError("preference profile does not exist")
    if mutation.kind == "record":
        active = tuple(
            session.scalars(
                select(PreferenceExpressionModel)
                .where(
                    PreferenceExpressionModel.profile_id
                    == mutation.expression.profile_id,
                    PreferenceExpressionModel.subject_key
                    == mutation.expression.subject_key,
                    PreferenceExpressionModel.status == "active",
                )
                .order_by(PreferenceExpressionModel.id)
                .with_for_update()
            )
        )
        if active:
            raise RuntimeError("preference subject already has an active expression")
        return None, ()

    if mutation.previous_expression_id is None:
        raise RuntimeError("preference mutation requires a predecessor")
    predecessor = session.scalar(
        select(PreferenceExpressionModel)
        .where(PreferenceExpressionModel.id == mutation.previous_expression_id)
        .order_by(PreferenceExpressionModel.id)
        .with_for_update()
    )
    if (
        predecessor is None
        or predecessor.status != "active"
        or predecessor.profile_id != mutation.expression.profile_id
    ):
        raise RuntimeError("preference predecessor is not active")

    requested_ids = tuple(
        sorted(
            (item.previous_binding_id for item in mutation.binding_supersessions),
            key=str,
        )
    )
    retired = tuple(
        session.scalars(
            select(CriterionBindingModel)
            .where(
                CriterionBindingModel.expression_id == predecessor.id,
                CriterionBindingModel.status == "active",
            )
            .order_by(CriterionBindingModel.id)
            .with_for_update()
        )
    )
    active_ids = {binding.id for binding in retired}
    if (
        set(requested_ids) != active_ids
        or len(retired) != len(requested_ids)
        or any(
            binding.status != "active"
            or binding.expression_id != predecessor.id
            for binding in retired
        )
    ):
        raise RuntimeError("preference binding lineage is stale")
    new_binding_ids = {binding.binding_id for binding in mutation.bindings}
    if any(
        item.replacement_binding_id is not None
        and item.replacement_binding_id not in new_binding_ids
        for item in mutation.binding_supersessions
    ):
        raise RuntimeError("preference binding successor is not in mutation")
    return predecessor, retired


def _retire_predecessor(
    predecessor: PreferenceExpressionModel | None,
    retired_bindings: tuple[CriterionBindingModel, ...],
    mutation: PreferenceMutation,
) -> None:
    if predecessor is None:
        return
    retired_at = datetime.now(timezone.utc)
    successor_by_binding = {
        item.previous_binding_id: item.replacement_binding_id
        for item in mutation.binding_supersessions
    }
    predecessor.status = "withdrawn" if mutation.kind == "withdraw" else "superseded"
    predecessor.superseded_by = (
        None if mutation.kind == "withdraw" else mutation.expression.expression_id
    )
    predecessor.updated_at = retired_at
    predecessor.actor_kind = mutation.expression.actor_kind
    predecessor.actor_id = mutation.expression.actor_id
    predecessor.correlation_id = mutation.expression.correlation_id
    for binding in retired_bindings:
        binding.status = "superseded"
        binding.superseded_by = successor_by_binding[binding.id]
        binding.updated_at = retired_at
        binding.actor_kind = mutation.expression.actor_kind
        binding.actor_id = mutation.expression.actor_id
        binding.correlation_id = mutation.expression.correlation_id


def _retire_facts(
    retired_bindings: tuple[CriterionBindingModel, ...],
    mutation: PreferenceMutation,
    new_fact_ids: Mapping[UUID, UUID],
    session: Session,
) -> None:
    if retired_bindings:
        successor_by_binding = {
            item.previous_binding_id: item.replacement_binding_id
            for item in mutation.binding_supersessions
        }
        retired_at = datetime.now(timezone.utc)
        facts = tuple(
            session.scalars(
                select(PreferenceFact)
                .where(
                    PreferenceFact.criterion_binding_id.in_(
                        binding.id for binding in retired_bindings
                    ),
                    PreferenceFact.state == "active",
                )
                .order_by(PreferenceFact.id)
                .with_for_update()
            )
        )
        for fact in facts:
            replacement_binding_id = successor_by_binding[
                cast(UUID, fact.criterion_binding_id)
            ]
            fact.state = "superseded"
            fact.superseded_by = (
                new_fact_ids.get(replacement_binding_id)
                if replacement_binding_id is not None
                else None
            )
            fact.updated_at = retired_at
            fact.actor_kind = mutation.expression.actor_kind
            fact.actor_id = mutation.expression.actor_id
            fact.correlation_id = mutation.expression.correlation_id
        session.flush()


def _expression_model(expression: PreferenceExpression) -> PreferenceExpressionModel:
    return PreferenceExpressionModel(
        id=expression.expression_id,
        created_at=expression.created_at,
        updated_at=expression.created_at,
        actor_kind=expression.actor_kind,
        actor_id=expression.actor_id,
        source="preferences.expression",
        correlation_id=expression.correlation_id,
        profile_id=expression.profile_id,
        source_message_id=expression.source_message_id,
        source_kind=expression.source_kind,
        subject_key=expression.subject_key,
        raw_text=expression.raw_text,
        authority=expression.authority,
        status=expression.status,
        superseded_by=expression.superseded_by,
        original_text_available=expression.original_text_available,
    )


def _binding_model(binding: CriterionBinding) -> CriterionBindingModel:
    return CriterionBindingModel(
        id=binding.binding_id,
        created_at=binding.created_at,
        updated_at=binding.created_at,
        actor_kind=binding.actor_kind,
        actor_id=binding.actor_id,
        source="preferences.binding",
        correlation_id=binding.correlation_id,
        expression_id=binding.expression_id,
        kind=binding.kind,
        concept_key=binding.concept_key,
        matcher_type=binding.matcher_type,
        mode=binding.mode,
        params=dict(binding.params),
        confidence=binding.confidence,
        evidence_refs=[dict(item) for item in binding.evidence_refs],
        limitations=list(binding.limitations),
        interpretation_version=binding.interpretation_version,
        query_embedding=(
            list(binding.query_embedding)
            if binding.query_embedding is not None
            else None
        ),
        embedding_version_id=binding.embedding_version_id,
        status=binding.status,
        superseded_by=binding.superseded_by,
    )


def _fact_model(
    mutation: PreferenceMutation,
    binding: CriterionBinding,
    *,
    fact_id: UUID,
) -> PreferenceFact:
    params = dict(binding.params)
    value = params.get("value", params.get("preferred_value", params))
    return PreferenceFact(
        id=fact_id,
        created_at=binding.created_at,
        updated_at=binding.created_at,
        actor_kind=binding.actor_kind,
        actor_id=binding.actor_id,
        source="preferences.fact",
        correlation_id=binding.correlation_id,
        profile_id=mutation.expression.profile_id,
        concept_key=cast(str, binding.concept_key),
        value=value,
        weight=float(cast(int | float | str, params.get("weight", 1.0))),
        polarity=str(params.get("polarity", "positive")),
        confidence=binding.confidence,
        fact_source="preference_binding",
        state="active",
        superseded_by=None,
        criterion_binding_id=binding.binding_id,
        soft_to_hard=binding.mode == "hard",
    )


def _to_expression(model: PreferenceExpressionModel) -> PreferenceExpression:
    return PreferenceExpression(
        expression_id=model.id,
        profile_id=model.profile_id,
        source_message_id=model.source_message_id,
        source_kind=cast(PreferenceSourceKind, model.source_kind),
        subject_key=model.subject_key,
        raw_text=model.raw_text,
        authority=cast(PreferenceAuthority, model.authority),
        status=cast(PreferenceStatus, model.status),
        superseded_by=model.superseded_by,
        original_text_available=model.original_text_available,
        created_at=model.created_at,
        correlation_id=model.correlation_id,
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
    )


def _to_binding(model: CriterionBindingModel) -> CriterionBinding:
    raw_embedding = model.query_embedding
    return CriterionBinding(
        binding_id=model.id,
        expression_id=model.expression_id,
        kind=cast(BindingKind, model.kind),
        concept_key=model.concept_key,
        matcher_type=cast(MatcherType | None, model.matcher_type),
        mode=cast(BindingMode, model.mode),
        params=dict(model.params or {}),
        confidence=float(model.confidence),
        evidence_refs=tuple(dict(item) for item in (model.evidence_refs or [])),
        limitations=tuple(model.limitations or []),
        interpretation_version=model.interpretation_version,
        query_embedding=(
            tuple(float(value) for value in raw_embedding)
            if raw_embedding is not None
            else None
        ),
        embedding_version_id=model.embedding_version_id,
        status=cast(BindingStatus, model.status),
        superseded_by=model.superseded_by,
        created_at=model.created_at,
        correlation_id=model.correlation_id,
        actor_kind=model.actor_kind,
        actor_id=model.actor_id,
    )
