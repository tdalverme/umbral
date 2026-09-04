"""Explicit application adapters executing V5 radar commands.

The executor routes typed commands to the existing application services only:
it creates and binds a radar through ``ChatService``/``RadarService`` and
creates durable hard-filter proposals through
``SearchProfileUpdateProposals.propose``. It never touches repositories
directly and never caches idempotency in the agent.
"""

from __future__ import annotations

from uuid import UUID

from umbral.application.agent.tools.contracts import (
    Proposal,
    ProposalNotFound,
    ProposalNotPending,
)
from umbral.application.agent.tools.proposals import (
    SearchProfileUpdateProposals,
)
from umbral.application.chat.service import ChatService
from umbral.application.conversation.v5.contracts import (
    ClearFilterCommand,
    CommandV5,
    ConceptLinkV5,
    CreateRadarCommand,
    ExecutedActV5,
    RecordDesireCommand,
    RecordFeedbackCommand,
    ReviseDesireCommand,
    SetFilterCommand,
    TurnContextV5,
    WithdrawDesireCommand,
)
from umbral.application.conversation.v5.ports import FeedbackRecorderV5
from umbral.application.preferences.contracts import (
    BindingDraft,
    PreferenceValidationError,
)
from umbral.application.preferences.intensity import IntensityPolicy
from umbral.application.preferences.ports import ConceptReader
from umbral.application.radar.service import RadarService
from umbral.infrastructure.conversation.composition import PreferenceServiceLike


class EffectExecutorV5:
    """Executes V5 commands through the explicit application interfaces."""

    def __init__(
        self,
        *,
        radar: RadarService,
        chat: ChatService,
        proposals: SearchProfileUpdateProposals,
        preferences: PreferenceServiceLike | None = None,
        feedback: FeedbackRecorderV5 | None = None,
        concepts: ConceptReader | None = None,
        intensity_policy: IntensityPolicy | None = None,
        radar_name: str = "Mi búsqueda",
    ) -> None:
        self.radar = radar
        self.chat = chat
        self.proposals = proposals
        self.preferences = preferences
        self.feedback = feedback
        self.concepts = concepts
        self.intensity_policy = intensity_policy
        self.radar_name = radar_name

    def execute(
        self,
        *,
        command: CommandV5,
        context: TurnContextV5,
        idempotency_key: str,
    ) -> ExecutedActV5:
        match command:
            case CreateRadarCommand():
                return self._create_radar(command, context)
            case SetFilterCommand():
                return self._set_filter(command, context)
            case ClearFilterCommand():
                return self._clear_filter(command, context)
            case RecordDesireCommand():
                return self._record_desire(command, context)
            case ReviseDesireCommand():
                return self._revise_desire(command, context)
            case WithdrawDesireCommand():
                return self._withdraw_desire(command, context)
            case RecordFeedbackCommand():
                return self._record_feedback(command, context, idempotency_key)

    def _create_radar(
        self, command: CreateRadarCommand, context: TurnContextV5
    ) -> ExecutedActV5:
        user_id = UUID(context.user_id)
        session_id = UUID(context.session_id)
        correlation_id = UUID(context.correlation_id)
        session = self.chat.get_session(user_id=user_id, session_id=session_id)
        if session.search_profile_id is not None:
            # The durable session binding is the native idempotency mechanism:
            # one radar per session, so a replay returns the existing radar.
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="radar.created",
                object_ref=f"radar:{session.search_profile_id}",
            )
        profile, _run = self.radar.create_profile(
            owner_id=user_id,
            name=command.name or self.radar_name,
            zones=(),
            budget_max=None,
            budget_min=None,
            min_rooms=None,
            surface_min=None,
            surface_max=None,
            unknown_strategy=None,
            correlation_id=correlation_id,
        )
        self.chat.bind_profile(
            user_id=user_id,
            session_id=session_id,
            search_profile_id=profile.profile_id,
            correlation_id=correlation_id,
        )
        return ExecutedActV5(
            act_id=command.act_id,
            effect_key="radar.created",
            object_ref=f"radar:{profile.profile_id}",
        )

    def _set_filter(
        self, command: SetFilterCommand, context: TurnContextV5
    ) -> ExecutedActV5:
        profile_id = _profile_id(context)
        if profile_id is None:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="filter.set",
                status="rejected",
                reason_code="radar.not_bound",
            )
        return self._propose(
            command.act_id,
            effect_key="filter.set",
            context=context,
            profile_id=profile_id,
            change=_filter_change(command.filter_key, command.value),
            reason_code="filter.requires_confirmation",
        )

    def _clear_filter(
        self, command: ClearFilterCommand, context: TurnContextV5
    ) -> ExecutedActV5:
        profile_id = _profile_id(context)
        if profile_id is None:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="filter.cleared",
                status="rejected",
                reason_code="radar.not_bound",
            )
        return self._propose(
            command.act_id,
            effect_key="filter.cleared",
            context=context,
            profile_id=profile_id,
            change=_clear_change(command.filter_key),
            reason_code="filter.requires_confirmation",
        )

    def _record_desire(
        self, command: RecordDesireCommand, context: TurnContextV5
    ) -> ExecutedActV5:
        profile_id = _profile_id(context)
        if profile_id is None:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="desire.remembered",
                status="rejected",
                reason_code="radar.not_bound",
            )
        preferences = self.preferences
        if preferences is None:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="desire.remembered",
                status="rejected",
                reason_code="preferences.not_configured",
            )
        if not command.concept_links:
            change = preferences.record_expression(
                profile_id=profile_id,
                source_message_id=None,
                subject_key=command.subject_ref,
                raw_text=command.raw_text,
                authority="explicit",
                binding_drafts=(BindingDraft.unresolved("no_structured_evidence"),),
                correlation_id=UUID(context.correlation_id),
            )
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="desire.remembered",
                object_ref=f"desire:{change.expression.expression_id}",
            )
        drafts = self._binding_drafts(command.concept_links)
        if drafts is None:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="desire.remembered",
                status="rejected",
                reason_code="preferences.structured_concept_not_found",
            )
        try:
            changes = tuple(
                preferences.set_explicit_preference(
                    profile_id=profile_id,
                    source_message_id=None,
                    concept_key=link.concept_ref,
                    raw_text=command.raw_text,
                    binding_draft=draft,
                    correlation_id=UUID(context.correlation_id),
                )
                for link, draft in zip(command.concept_links, drafts, strict=True)
            )
        except (PreferenceValidationError, RuntimeError):
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="desire.remembered",
                status="rejected",
                reason_code="preference.already_active",
            )
        return ExecutedActV5(
            act_id=command.act_id,
            effect_key="desire.remembered",
            object_ref=f"desire:{changes[-1].expression.expression_id}",
        )

    def _revise_desire(
        self, command: ReviseDesireCommand, context: TurnContextV5
    ) -> ExecutedActV5:
        profile_id = _profile_id(context)
        if profile_id is None:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="desire.revised",
                status="rejected",
                reason_code="radar.not_bound",
            )
        preferences = self.preferences
        if preferences is None:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="desire.revised",
                status="rejected",
                reason_code="preferences.not_configured",
            )
        drafts = self._binding_drafts(command.concept_links)
        if drafts is None:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="desire.revised",
                status="rejected",
                reason_code="preferences.structured_concept_not_found",
            )
        change = preferences.revise_expression(
            profile_id=profile_id,
            previous_expression_id=_ref_uuid(command.desire_ref, "desire"),
            source_message_id=None,
            raw_text=command.raw_text,
            authority="explicit",
            binding_drafts=drafts,
            correlation_id=UUID(context.correlation_id),
        )
        return ExecutedActV5(
            act_id=command.act_id,
            effect_key="desire.revised",
            object_ref=f"desire:{change.expression.expression_id}",
        )

    def _withdraw_desire(
        self, command: WithdrawDesireCommand, context: TurnContextV5
    ) -> ExecutedActV5:
        profile_id = _profile_id(context)
        if profile_id is None:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="desire.withdrawn",
                status="rejected",
                reason_code="radar.not_bound",
            )
        preferences = self.preferences
        if preferences is None:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="desire.withdrawn",
                status="rejected",
                reason_code="preferences.not_configured",
            )
        change = preferences.withdraw_expression(
            profile_id=profile_id,
            expression_id=_ref_uuid(command.desire_ref, "desire"),
            correlation_id=UUID(context.correlation_id),
        )
        return ExecutedActV5(
            act_id=command.act_id,
            effect_key="desire.withdrawn",
            object_ref=f"desire:{change.expression.expression_id}",
        )

    def _record_feedback(
        self,
        command: RecordFeedbackCommand,
        context: TurnContextV5,
        idempotency_key: str,
    ) -> ExecutedActV5:
        profile_id = _profile_id(context)
        if profile_id is None:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="feedback.recorded",
                status="rejected",
                reason_code="radar.not_bound",
            )
        feedback = self.feedback
        if feedback is None:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="feedback.recorded",
                status="rejected",
                reason_code="feedback.not_configured",
            )
        feedback.record_feedback(
            owner_id=UUID(context.user_id),
            profile_id=profile_id,
            listing_id=command.listing_id,
            run_id=None,
            event_type=command.feedback_type,
            reason_keys=(),
            idempotency_key=idempotency_key,
            correlation_id=UUID(context.correlation_id),
            free_feedback=command.raw_text,
        )
        return ExecutedActV5(
            act_id=command.act_id,
            effect_key="feedback.recorded",
            object_ref=f"listing:{command.listing_id}",
        )

    def _binding_drafts(
        self, concept_links: tuple[ConceptLinkV5, ...]
    ) -> tuple[BindingDraft, ...] | None:
        if not concept_links:
            return (BindingDraft.unresolved("no_structured_evidence"),)
        if self.concepts is None or self.intensity_policy is None:
            return None
        drafts: list[BindingDraft] = []
        for link in concept_links:
            concept = self.concepts.get(link.concept_ref)
            if concept is None:
                return None
            drafts.append(
                BindingDraft.structured(
                    concept_key=concept.key,
                    matcher_type=concept.matcher_type,
                    params={
                        "polarity": link.polarity,
                        "intensity": link.intensity,
                        "weight": self.intensity_policy.weight_for(link.intensity),
                        "intensity_policy_version": self.intensity_policy.version,
                    },
                    confidence=link.confidence,
                    mode="soft",
                    evidence_refs=tuple(
                        {
                            "kind": "message_span",
                            "start": span.start,
                            "end": span.end,
                            "text": span.text,
                        }
                        for span in link.evidence_spans
                    ),
                )
            )
        return tuple(drafts)

    def _propose(
        self,
        act_id: str,
        *,
        effect_key: str,
        context: TurnContextV5,
        profile_id: UUID,
        change: dict[str, object],
        reason_code: str,
    ) -> ExecutedActV5:
        proposal = self._correct_active_proposal(
            act_id=act_id, context=context, profile_id=profile_id, change=change
        )
        return ExecutedActV5(
            act_id=act_id,
            effect_key=effect_key,
            status="pending",
            object_ref=f"proposal:{proposal.proposal_id}",
            reason_code=reason_code,
        )

    def _correct_active_proposal(
        self,
        *,
        act_id: str,
        context: TurnContextV5,
        profile_id: UUID,
        change: dict[str, object],
    ) -> Proposal:
        pending = context.pending_action
        if pending is not None:
            try:
                current = self.proposals.get(
                    user_id=UUID(context.user_id),
                    session_id=UUID(context.session_id),
                    search_profile_id=profile_id,
                    proposal_id=_ref_uuid(pending.pending_ref, "pending"),
                )
            except ProposalNotFound:
                current = None
            if current is not None and set(current.diff) == set(change):
                return self.proposals.derive(
                    user_id=UUID(context.user_id),
                    session_id=UUID(context.session_id),
                    search_profile_id=profile_id,
                    proposal_id=current.proposal_id,
                    change=change,
                    correlation_id=UUID(context.correlation_id),
                    source_act_id=act_id,
                )
        return self.proposals.propose(
            user_id=UUID(context.user_id),
            session_id=UUID(context.session_id),
            search_profile_id=profile_id,
            change=change,
            correlation_id=UUID(context.correlation_id),
            source_act_id=act_id,
        )


class ProposalsPendingResolverV5:
    """Resolves the durable pending proposal through its native service."""

    def __init__(self, *, proposals: SearchProfileUpdateProposals) -> None:
        self.proposals = proposals

    def resolve(
        self,
        *,
        act_id: str,
        context: TurnContextV5,
        pending_ref: str,
        decision: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> ExecutedActV5:
        profile_id = _profile_id(context)
        if profile_id is None:
            return ExecutedActV5(
                act_id=act_id,
                effect_key="pending.resolved",
                status="rejected",
                reason_code="radar.not_bound",
            )
        pending_id = _ref_uuid(pending_ref, "pending")
        if decision == "approve":
            try:
                self.proposals.apply(
                    user_id=UUID(context.user_id),
                    session_id=UUID(context.session_id),
                    search_profile_id=profile_id,
                    proposal_id=pending_id,
                    confirmation=True,
                    idempotency_key=idempotency_key,
                    correlation_id=correlation_id,
                )
            except ProposalNotPending:
                current = self.proposals.get(
                    user_id=UUID(context.user_id),
                    session_id=UUID(context.session_id),
                    search_profile_id=profile_id,
                    proposal_id=pending_id,
                )
                return ExecutedActV5(
                    act_id=act_id,
                    effect_key="pending.resolved",
                    status=("rejected" if current.state == "rejected" else "applied"),
                    object_ref=f"pending:{pending_id}",
                    reason_code=current.rejection_reason,
                )
            return ExecutedActV5(
                act_id=act_id,
                effect_key="pending.resolved",
                object_ref=f"radar:{profile_id}",
            )
        rejected = self.proposals.reject(
            user_id=UUID(context.user_id),
            session_id=UUID(context.session_id),
            search_profile_id=profile_id,
            proposal_id=pending_id,
            note="rechazado desde el chat",
            correlation_id=correlation_id,
        )
        return ExecutedActV5(
            act_id=act_id,
            effect_key="pending.resolved",
            status="rejected" if rejected.state == "rejected" else "applied",
            object_ref=f"pending:{pending_id}",
            reason_code=rejected.rejection_reason,
        )


def _profile_id(context: TurnContextV5) -> UUID | None:
    if context.active_radar_ref is None:
        return None
    try:
        return UUID(context.active_radar_ref.removeprefix("radar:"))
    except ValueError:
        return None


def _ref_uuid(ref: str, prefix: str) -> UUID:
    return UUID(ref.removeprefix(f"{prefix}:"))


def _current_value(context: TurnContextV5, filter_key: str) -> object | None:
    for filter_view in context.current_filters:
        if filter_view.filter_key == filter_key:
            return filter_view.value
    return None


def _filter_change(filter_key: str, value: object) -> dict[str, object]:
    if filter_key == "budget_max":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return {}
        return {"budget_max": float(value)}
    if filter_key == "min_rooms":
        if isinstance(value, bool) or not isinstance(value, int):
            return {}
        return {"min_rooms": int(value)}
    if filter_key == "zones":
        if not isinstance(value, tuple):
            return {}
        return {"zones": list(value)}
    return {}


def _clear_change(filter_key: str) -> dict[str, object]:
    if filter_key == "budget_max":
        return {"budget_max": None}
    if filter_key == "min_rooms":
        return {"min_rooms": None}
    if filter_key == "zones":
        return {"zones": []}
    return {}
