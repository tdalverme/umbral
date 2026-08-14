"""In-memory atomic preference store for application-service unit tests."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from uuid import UUID, uuid4

from umbral.application.preferences.contracts import (
    CriterionBinding,
    PreferenceConcept,
    PreferenceExpression,
    PreferenceMutation,
    PreferenceMutationResult,
)


@dataclass
class FakePreferenceStore:
    expressions: list[PreferenceExpression] = field(default_factory=list)
    bindings: list[CriterionBinding] = field(default_factory=list)
    commands: list[PreferenceMutation] = field(default_factory=list)
    fail_next_mutation: bool = False

    def apply(self, mutation: PreferenceMutation) -> PreferenceMutationResult:
        if self.fail_next_mutation:
            self.fail_next_mutation = False
            raise RuntimeError("injected preference mutation failure")

        expressions = list(self.expressions)
        bindings = list(self.bindings)
        fact_ids = tuple(uuid4() for _ in mutation.fact_binding_ids)
        if mutation.kind == "record":
            expressions.append(mutation.expression)
            bindings.extend(mutation.bindings)
        elif mutation.kind == "revise":
            expressions = [
                replace(
                    expression,
                    status="superseded",
                    superseded_by=mutation.expression.expression_id,
                )
                if expression.expression_id == mutation.previous_expression_id
                else expression
                for expression in expressions
            ]
            bindings = _supersede_bindings(bindings, mutation)
            expressions.append(mutation.expression)
            bindings.extend(mutation.bindings)
        else:
            expressions = [
                mutation.expression
                if expression.expression_id == mutation.expression.expression_id
                else expression
                for expression in expressions
            ]
            bindings = _supersede_bindings(bindings, mutation)

        self.expressions = expressions
        self.bindings = bindings
        self.commands.append(mutation)
        return PreferenceMutationResult(fact_ids=fact_ids)

    def get(self, expression_id: UUID) -> PreferenceExpression | None:
        return next(
            (item for item in self.expressions if item.expression_id == expression_id),
            None,
        )

    def active_for_profile(self, profile_id: UUID) -> tuple[PreferenceExpression, ...]:
        return tuple(
            item
            for item in self.expressions
            if item.profile_id == profile_id and item.status == "active"
        )

    def active_for_expression_ids(
        self, expression_ids: tuple[UUID, ...]
    ) -> tuple[CriterionBinding, ...]:
        return tuple(
            item
            for item in self.bindings
            if item.expression_id in expression_ids and item.status == "active"
        )


def _supersede_bindings(
    bindings: list[CriterionBinding], mutation: PreferenceMutation
) -> list[CriterionBinding]:
    successors = {
        item.previous_binding_id: item.replacement_binding_id
        for item in mutation.binding_supersessions
    }
    return [
        replace(
            binding,
            status="superseded",
            superseded_by=successors[binding.binding_id],
        )
        if binding.binding_id in successors
        else binding
        for binding in bindings
    ]


@dataclass
class FakeConceptReader:
    rows: dict[str, PreferenceConcept] = field(default_factory=dict)

    def get(self, concept_key: str) -> PreferenceConcept | None:
        return self.rows.get(concept_key)
