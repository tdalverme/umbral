"""Application service for atomic preference expressions and binding lineage."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from umbral.application.preferences.contracts import (
    BindingDraft,
    BindingSupersession,
    CriterionBinding,
    PreferenceAuthority,
    PreferenceAuthorityError,
    PreferenceChange,
    PreferenceExpression,
    PreferenceMutation,
    PreferenceNotFound,
    PreferencePolicySpec,
    PreferenceValidationError,
    PreferenceView,
)
from umbral.application.preferences.policy import can_supersede, validate_binding
from umbral.application.preferences.ports import (
    BindingReader,
    ConceptReader,
    ExpressionReader,
    PreferenceMutationPort,
)

Clock = Callable[[], datetime]
BindingIdentity = tuple[str, str | None, str | None, str]


class PreferenceService:
    """Preserve statements while delegating each state transition to one port."""

    def __init__(
        self,
        *,
        expressions: ExpressionReader,
        bindings: BindingReader,
        mutations: PreferenceMutationPort,
        concepts: ConceptReader,
        policy: PreferencePolicySpec,
        clock: Clock | None = None,
        interpretation_version: str = "preference-binding-v1",
    ) -> None:
        self.expressions = expressions
        self.bindings = bindings
        self.mutations = mutations
        self.concepts = concepts
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
        """Append an expression, its bindings, and computable facts atomically."""

        self._validate_drafts(binding_drafts, authority)
        expression = self._new_expression(
            profile_id=profile_id,
            source_message_id=source_message_id,
            subject_key=subject_key,
            raw_text=raw_text,
            authority=authority,
            correlation_id=correlation_id,
        )
        bindings = self._create_bindings(expression, binding_drafts)
        result = self.mutations.apply(
            PreferenceMutation(
                kind="record",
                expression=expression,
                bindings=bindings,
                fact_binding_ids=self._fact_binding_ids(bindings),
            )
        )
        return PreferenceChange(expression, bindings, result.fact_ids)

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
        """Atomically append a successor and retire its expression and bindings."""

        previous = self._active_expression(profile_id, previous_expression_id)
        if not can_supersede(previous.authority, authority):
            raise PreferenceAuthorityError(
                f"{authority} cannot supersede {previous.authority}"
            )
        self._validate_drafts(binding_drafts, authority)
        expression = self._new_expression(
            profile_id=profile_id,
            source_message_id=source_message_id,
            subject_key=previous.subject_key,
            raw_text=raw_text,
            authority=authority,
            correlation_id=correlation_id,
        )
        bindings = self._create_bindings(expression, binding_drafts)
        previous_bindings = self.bindings.active_for_expression_ids(
            (previous.expression_id,)
        )
        result = self.mutations.apply(
            PreferenceMutation(
                kind="revise",
                expression=expression,
                bindings=bindings,
                fact_binding_ids=self._fact_binding_ids(bindings),
                previous_expression_id=previous.expression_id,
                binding_supersessions=self._binding_supersessions(
                    previous_bindings, bindings
                ),
            )
        )
        return PreferenceChange(expression, bindings, result.fact_ids)

    def withdraw_expression(
        self,
        *,
        profile_id: UUID,
        expression_id: UUID,
        correlation_id: UUID,
    ) -> PreferenceChange:
        """Atomically retire an expression and every active binding without deletion."""

        expression = self._active_expression(profile_id, expression_id)
        active_bindings = self.bindings.active_for_expression_ids((expression_id,))
        withdrawn = replace(expression, status="withdrawn")
        self.mutations.apply(
            PreferenceMutation(
                kind="withdraw",
                expression=withdrawn,
                bindings=(),
                fact_binding_ids=(),
                previous_expression_id=expression_id,
                binding_supersessions=tuple(
                    BindingSupersession(binding.binding_id, None)
                    for binding in active_bindings
                ),
            )
        )
        return PreferenceChange(
            withdrawn,
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

    def _validate_drafts(
        self, drafts: tuple[BindingDraft, ...], authority: PreferenceAuthority
    ) -> None:
        errors: list[str] = []
        for draft in drafts:
            errors.extend(validate_binding(draft, self.policy))
            if authority == "passive" and draft.mode == "hard":
                errors.append("preferences.passive_hard_binding_forbidden")
            if draft.kind == "structured":
                concept = self.concepts.get(draft.concept_key or "")
                if concept is None:
                    errors.append("preferences.structured_concept_not_found")
                elif concept.matcher_type != draft.matcher_type:
                    errors.append("preferences.structured_matcher_mismatch")
        if errors:
            raise PreferenceValidationError(tuple(errors))

    def _new_expression(
        self,
        *,
        profile_id: UUID,
        source_message_id: UUID | None,
        subject_key: str,
        raw_text: str,
        authority: PreferenceAuthority,
        correlation_id: UUID,
    ) -> PreferenceExpression:
        return PreferenceExpression(
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
                evidence_refs=_binding_evidence_refs(draft),
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

    def _fact_binding_ids(
        self, bindings: tuple[CriterionBinding, ...]
    ) -> tuple[UUID, ...]:
        return tuple(
            binding.binding_id
            for binding in bindings
            if binding.kind == "structured"
            and binding.concept_key is not None
            and (concept := self.concepts.get(binding.concept_key)) is not None
            and concept.computable
        )

    def _binding_supersessions(
        self,
        previous: tuple[CriterionBinding, ...],
        replacement: tuple[CriterionBinding, ...],
    ) -> tuple[BindingSupersession, ...]:
        successors: dict[BindingIdentity, list[CriterionBinding]] = defaultdict(list)
        for binding in replacement:
            successors[_binding_identity(binding)].append(binding)
        return tuple(
            BindingSupersession(
                previous_binding_id=binding.binding_id,
                replacement_binding_id=(
                    successors[_binding_identity(binding)].pop(0).binding_id
                    if successors[_binding_identity(binding)]
                    else None
                ),
            )
            for binding in previous
        )

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


def _binding_evidence_refs(draft: BindingDraft) -> tuple[dict[str, object], ...]:
    refs = tuple(dict(ref) for ref in draft.evidence_refs)
    if draft.confirmation is None:
        return refs
    confirmation_ref: dict[str, object] = {
        "kind": "hard_confirmation",
        "action_id": str(draft.confirmation.action_id),
    }
    return (*refs, confirmation_ref)


def _binding_identity(binding: CriterionBinding) -> BindingIdentity:
    return (binding.kind, binding.concept_key, binding.matcher_type, binding.mode)
