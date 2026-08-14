"""Application service for append-only preference expressions and bindings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from umbral.application.preferences.contracts import (
    BindingDraft,
    CriterionBinding,
    PreferenceAuthority,
    PreferenceAuthorityError,
    PreferenceChange,
    PreferenceExpression,
    PreferenceNotFound,
    PreferencePolicySpec,
    PreferenceValidationError,
    PreferenceView,
)
from umbral.application.preferences.policy import can_supersede, validate_binding
from umbral.application.preferences.ports import (
    BindingRepository,
    ConceptReader,
    ExpressionRepository,
    FactWriter,
)

Clock = Callable[[], datetime]


class PreferenceService:
    """Preserve every expression while emitting facts only from valid capabilities."""

    def __init__(
        self,
        *,
        expressions: ExpressionRepository,
        bindings: BindingRepository,
        concepts: ConceptReader,
        facts: FactWriter,
        policy: PreferencePolicySpec,
        clock: Clock | None = None,
        interpretation_version: str = "preference-binding-v1",
    ) -> None:
        self.expressions = expressions
        self.bindings = bindings
        self.concepts = concepts
        self.facts = facts
        self.policy = policy
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.interpretation_version = interpretation_version

    def record_expression(
        self,
        *,
        profile_id: UUID,
        source_message_id: UUID | None,
        subject_key: str,
        raw_text: str,
        authority: PreferenceAuthority,
        binding_drafts: tuple[BindingDraft, ...],
        correlation_id: UUID,
    ) -> PreferenceChange:
        """Append a complete statement and every valid interpretation of it."""

        self._validate_drafts(binding_drafts)
        expression = PreferenceExpression(
            expression_id=uuid4(),
            profile_id=profile_id,
            source_message_id=source_message_id,
            source_kind="chat",
            subject_key=subject_key,
            raw_text=raw_text,
            authority=authority,
            status="active",
            superseded_by=None,
            original_text_available=True,
            created_at=self.clock(),
            correlation_id=correlation_id,
        )
        bindings = self._create_bindings(expression, binding_drafts)
        self.expressions.insert(expression)
        self.bindings.insert_many(bindings)
        fact_ids = self._record_facts(expression, bindings)
        return PreferenceChange(expression, bindings, fact_ids)

    def revise_expression(
        self,
        *,
        profile_id: UUID,
        previous_expression_id: UUID,
        source_message_id: UUID | None,
        raw_text: str,
        authority: PreferenceAuthority,
        binding_drafts: tuple[BindingDraft, ...],
        correlation_id: UUID,
    ) -> PreferenceChange:
        """Replace one active expression only when its authority permits it."""

        previous = self._active_expression(profile_id, previous_expression_id)
        if not can_supersede(previous.authority, authority):
            raise PreferenceAuthorityError(
                f"{authority} cannot supersede {previous.authority}"
            )
        change = self.record_expression(
            profile_id=profile_id,
            source_message_id=source_message_id,
            subject_key=previous.subject_key,
            raw_text=raw_text,
            authority=authority,
            binding_drafts=binding_drafts,
            correlation_id=correlation_id,
        )
        self.expressions.supersede(
            previous.expression_id, change.expression.expression_id
        )
        self.bindings.supersede_for_expression(previous.expression_id)
        return change

    def withdraw_expression(
        self,
        *,
        profile_id: UUID,
        expression_id: UUID,
        correlation_id: UUID,
    ) -> PreferenceChange:
        """Withdraw an active expression without deleting its source wording."""

        expression = self._active_expression(profile_id, expression_id)
        active_bindings = self.bindings.active_for_expression_ids((expression_id,))
        self.expressions.withdraw(expression_id)
        self.bindings.supersede_for_expression(expression_id)
        return PreferenceChange(
            replace(expression, status="withdrawn"),
            tuple(replace(binding, status="superseded") for binding in active_bindings),
            (),
        )

    def active_view(self, profile_id: UUID) -> tuple[PreferenceView, ...]:
        """Return active inspection data without leaking private query vectors."""

        expressions = self.expressions.active_for_profile(profile_id)
        if not expressions:
            return ()
        by_id = {expression.expression_id: expression for expression in expressions}
        bindings = self.bindings.active_for_expression_ids(tuple(by_id))
        return tuple(
            PreferenceView(
                expression_id=expression.expression_id,
                raw_text=expression.raw_text,
                subject_key=expression.subject_key,
                status=expression.status,
                binding_id=binding.binding_id,
                binding_kind=binding.kind,
                mode=binding.mode,
                confidence=binding.confidence,
                limitations=binding.limitations,
                evidence_refs=binding.evidence_refs,
            )
            for binding in bindings
            if (expression := by_id.get(binding.expression_id)) is not None
        )

    def _validate_drafts(self, drafts: tuple[BindingDraft, ...]) -> None:
        errors: list[str] = []
        for draft in drafts:
            errors.extend(validate_binding(draft, self.policy))
            if draft.mode == "hard":
                errors.append("preferences.hard_binding_requires_confirmation")
            if draft.kind == "structured":
                concept = self.concepts.get(draft.concept_key or "")
                if concept is None:
                    errors.append("preferences.structured_concept_not_found")
                elif concept.matcher_type != draft.matcher_type:
                    errors.append("preferences.structured_matcher_mismatch")
        if errors:
            raise PreferenceValidationError(tuple(errors))

    def _create_bindings(
        self,
        expression: PreferenceExpression,
        drafts: tuple[BindingDraft, ...],
    ) -> tuple[CriterionBinding, ...]:
        return tuple(
            CriterionBinding(
                binding_id=uuid4(),
                expression_id=expression.expression_id,
                kind=draft.kind,
                concept_key=draft.concept_key,
                matcher_type=draft.matcher_type,
                mode=draft.mode,
                params=dict(draft.params),
                confidence=draft.confidence,
                evidence_refs=draft.evidence_refs,
                limitations=draft.limitations,
                interpretation_version=self.interpretation_version,
                query_embedding=draft.query_embedding,
                embedding_version_id=draft.embedding_version_id,
                status="active",
                superseded_by=None,
                created_at=expression.created_at,
                correlation_id=expression.correlation_id,
            )
            for draft in drafts
        )

    def _record_facts(
        self,
        expression: PreferenceExpression,
        bindings: tuple[CriterionBinding, ...],
    ) -> tuple[UUID, ...]:
        fact_ids: list[UUID] = []
        for binding in bindings:
            if binding.kind != "structured" or binding.concept_key is None:
                continue
            concept = self.concepts.get(binding.concept_key)
            if concept is not None and concept.computable:
                fact_ids.append(
                    self.facts.record(expression=expression, binding=binding)
                )
        return tuple(fact_ids)

    def _active_expression(
        self, profile_id: UUID, expression_id: UUID
    ) -> PreferenceExpression:
        expression = self.expressions.get(expression_id)
        if (
            expression is None
            or expression.profile_id != profile_id
            or expression.status != "active"
        ):
            raise PreferenceNotFound(
                f"active preference expression not found: {expression_id}"
            )
        return expression
