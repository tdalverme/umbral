"""In-memory adapters for preference expression unit tests."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from uuid import UUID, uuid4

from umbral.application.preferences.contracts import (
    CriterionBinding,
    PreferenceConcept,
    PreferenceExpression,
)


@dataclass
class FakeExpressionRepository:
    rows: list[PreferenceExpression] = field(default_factory=list)

    def insert(self, expression: PreferenceExpression) -> None:
        self.rows.append(expression)

    def get(self, expression_id: UUID) -> PreferenceExpression | None:
        return next(
            (row for row in self.rows if row.expression_id == expression_id), None
        )

    def active_for_profile(self, profile_id: UUID) -> tuple[PreferenceExpression, ...]:
        return tuple(
            row
            for row in self.rows
            if row.profile_id == profile_id and row.status == "active"
        )

    def supersede(self, previous_id: UUID, replacement_id: UUID) -> None:
        self.rows = [
            replace(row, status="superseded", superseded_by=replacement_id)
            if row.expression_id == previous_id
            else row
            for row in self.rows
        ]

    def withdraw(self, expression_id: UUID) -> None:
        self.rows = [
            replace(row, status="withdrawn")
            if row.expression_id == expression_id
            else row
            for row in self.rows
        ]


@dataclass
class FakeBindingRepository:
    rows: list[CriterionBinding] = field(default_factory=list)

    def insert_many(self, bindings: tuple[CriterionBinding, ...]) -> None:
        self.rows.extend(bindings)

    def active_for_expression_ids(
        self, expression_ids: tuple[UUID, ...]
    ) -> tuple[CriterionBinding, ...]:
        return tuple(
            row
            for row in self.rows
            if row.expression_id in expression_ids and row.status == "active"
        )

    def supersede_for_expression(self, expression_id: UUID) -> None:
        self.rows = [
            replace(row, status="superseded")
            if row.expression_id == expression_id
            else row
            for row in self.rows
        ]


@dataclass
class FakeConceptReader:
    rows: dict[str, PreferenceConcept] = field(default_factory=dict)

    def get(self, concept_key: str) -> PreferenceConcept | None:
        return self.rows.get(concept_key)


@dataclass
class FakeFactWriter:
    binding_ids: list[UUID] = field(default_factory=list)

    def record(
        self, *, expression: PreferenceExpression, binding: CriterionBinding
    ) -> UUID:
        del expression
        self.binding_ids.append(binding.binding_id)
        return uuid4()
