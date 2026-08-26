"""Explicit application adapters executing V5 radar commands.

The executor routes typed commands to the existing application services only:
it creates and binds a radar through ``ChatService``/``RadarService``, applies
immediate new filters through ``RadarService.version_profile`` with the context
version, and creates durable material-change proposals through
``SearchProfileUpdateProposals.propose``. It never touches repositories
directly and never caches idempotency in the agent.
"""

from __future__ import annotations

from uuid import UUID

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
    ReviseDesireCommand,
    SetFilterCommand,
    TurnContextV5,
    WithdrawDesireCommand,
)
from umbral.application.preferences.contracts import BindingDraft
from umbral.application.radar.service import RadarService
from umbral.domain.errors import ConcurrencyConflict
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
        radar_name: str = "Mi búsqueda",
    ) -> None:
        self.radar = radar
        self.chat = chat
        self.proposals = proposals
        self.preferences = preferences
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
        current = _current_value(context, command.filter_key)
        if current is not None and current != command.value:
            return self._propose(
                command.act_id,
                effect_key="filter.set",
                context=context,
                profile_id=profile_id,
                change=_filter_change(command.filter_key, command.value),
                reason_code="filter.changes_existing_hard_filter",
            )
        if current == command.value:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="filter.set",
                object_ref=f"radar:{profile_id}",
            )
        try:
            self.radar.version_profile(
                owner_id=UUID(context.user_id),
                profile_id=profile_id,
                expected_version=command.expected_profile_version or 0,
                changes=_filter_change(command.filter_key, command.value),
                correlation_id=UUID(context.correlation_id),
            )
        except ConcurrencyConflict:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="filter.set",
                status="rejected",
                reason_code="execution.stale_context",
            )
        return ExecutedActV5(
            act_id=command.act_id,
            effect_key="filter.set",
            object_ref=f"radar:{profile_id}",
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
            reason_code="filter.removes_hard_filter",
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
        try:
            change = preferences.record_expression(
                profile_id=profile_id,
                source_message_id=None,
                subject_key=command.subject_ref,
                raw_text=command.raw_text,
                authority="explicit",
                binding_drafts=_binding_drafts(command.concept_links),
                correlation_id=UUID(context.correlation_id),
            )
        except RuntimeError:
            return ExecutedActV5(
                act_id=command.act_id,
                effect_key="desire.remembered",
                status="rejected",
                reason_code="preference.already_active",
            )
        return ExecutedActV5(
            act_id=command.act_id,
            effect_key="desire.remembered",
            object_ref=f"desire:{change.expression.expression_id}",
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
        change = preferences.revise_expression(
            profile_id=profile_id,
            previous_expression_id=_ref_uuid(command.desire_ref, "desire"),
            source_message_id=None,
            raw_text=command.raw_text,
            authority="explicit",
            binding_drafts=_binding_drafts(command.concept_links),
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
        proposal = self.proposals.propose(
            user_id=UUID(context.user_id),
            session_id=UUID(context.session_id),
            search_profile_id=profile_id,
            change=change,
            correlation_id=UUID(context.correlation_id),
        )
        return ExecutedActV5(
            act_id=act_id,
            effect_key=effect_key,
            status="pending",
            object_ref=f"proposal:{proposal.proposal_id}",
            reason_code=reason_code,
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


def _binding_drafts(
    concept_links: tuple[ConceptLinkV5, ...],
) -> tuple[BindingDraft, ...]:
    if not concept_links:
        return (BindingDraft.unresolved("no_structured_evidence"),)
    return tuple(
        BindingDraft.unresolved(f"concept_link:{link.concept_ref}")
        for link in concept_links
    )


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
