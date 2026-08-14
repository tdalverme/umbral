"""Ports used by the preference expression application service."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from umbral.application.preferences.contracts import (
    CriterionBinding,
    PreferenceConcept,
    PreferenceExpression,
    PreferenceMutation,
    PreferenceMutationResult,
)


class ExpressionReader(Protocol):
    def get(self, expression_id: UUID) -> PreferenceExpression | None: ...

    def active_for_profile(
        self, profile_id: UUID
    ) -> tuple[PreferenceExpression, ...]: ...

class BindingReader(Protocol):
    def active_for_expression_ids(
        self, expression_ids: tuple[UUID, ...]
    ) -> tuple[CriterionBinding, ...]: ...


class ConceptReader(Protocol):
    def get(self, concept_key: str) -> PreferenceConcept | None: ...


class PreferenceMutationPort(Protocol):
    def apply(self, mutation: PreferenceMutation) -> PreferenceMutationResult: ...


class PreferenceEmbeddingGateway(Protocol):
    def embed(self, text: str) -> tuple[tuple[float, ...], UUID]: ...
