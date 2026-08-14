"""Ports used by the preference expression application service."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from umbral.application.preferences.contracts import (
    CriterionBinding,
    PreferenceConcept,
    PreferenceExpression,
)


class ExpressionRepository(Protocol):
    def insert(self, expression: PreferenceExpression) -> None: ...

    def get(self, expression_id: UUID) -> PreferenceExpression | None: ...

    def active_for_profile(
        self, profile_id: UUID
    ) -> tuple[PreferenceExpression, ...]: ...

    def supersede(self, previous_id: UUID, replacement_id: UUID) -> None: ...

    def withdraw(self, expression_id: UUID) -> None: ...


class BindingRepository(Protocol):
    def insert_many(self, bindings: tuple[CriterionBinding, ...]) -> None: ...

    def active_for_expression_ids(
        self, expression_ids: tuple[UUID, ...]
    ) -> tuple[CriterionBinding, ...]: ...

    def supersede_for_expression(self, expression_id: UUID) -> None: ...


class ConceptReader(Protocol):
    def get(self, concept_key: str) -> PreferenceConcept | None: ...


class FactWriter(Protocol):
    def record(
        self, *, expression: PreferenceExpression, binding: CriterionBinding
    ) -> UUID: ...


class PreferenceEmbeddingGateway(Protocol):
    def embed(self, text: str) -> tuple[tuple[float, ...], UUID]: ...
