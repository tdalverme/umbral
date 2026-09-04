"""Infrastructure composition for the conversational copilot turn service.

Wires the durable conversation ports over the real application services: the
verified context reader resolves the chat session, its radar and the pending
action; the effect applier routes durable effects to RadarService and
PreferenceService; the refresh scheduler submits radar runs in the background.
No HTTP surface is wired here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, cast
from uuid import UUID

from umbral.application.agent.tools.proposals import (
    SearchProfileUpdateProposals,
)
from umbral.application.chat.contracts import ChatSessionNotFound
from umbral.application.chat.service import ChatService
from umbral.application.conversation.contracts import (
    ConversationError,
    ConversationNotReady,
    ConversationTurnContext,
    PendingAction,
    TurnEffect,
    TurnInterpretation,
)
from umbral.application.conversation.ports import (
    PendingActionReader,
)
from umbral.application.conversation.service import ConversationTurnService
from umbral.application.preferences.contracts import (
    BindingDraft,
    PreferenceAuthority,
    PreferenceChange,
    PreferenceView,
)
from umbral.application.radar.service import RadarService

Clock = Callable[[], datetime]


class PreferenceServiceLike(Protocol):
    """The preference service seam the copilot mutates through."""

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
    ) -> PreferenceChange: ...

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
    ) -> PreferenceChange: ...

    def set_explicit_preference(
        self,
        *,
        profile_id: UUID,
        source_message_id: UUID | None,
        concept_key: str,
        raw_text: str,
        binding_draft: BindingDraft,
        correlation_id: UUID,
    ) -> PreferenceChange: ...

    def withdraw_expression(
        self,
        *,
        profile_id: UUID,
        expression_id: UUID,
        correlation_id: UUID,
    ) -> PreferenceChange: ...

    def active_view(self, profile_id: UUID) -> tuple[PreferenceView, ...]: ...


@dataclass(frozen=True, slots=True)
class CopilotServices:
    """The explicit services the copilot may mutate through."""

    chat: ChatService
    radar: RadarService
    preferences: PreferenceServiceLike | None = None
    proposals: object | None = None


class SessionContextReader:
    """Resolves the verified conversation context from chat + radar state."""

    def __init__(
        self,
        *,
        chat: ChatService,
        radar: RadarService,
        pending: PendingActionReader,
        clock: Clock,
    ) -> None:
        self.chat = chat
        self.radar = radar
        self.pending = pending
        self.clock = clock

    def load(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        correlation_id: UUID,
    ) -> ConversationTurnContext:
        try:
            session = self.chat.get_session(user_id=user_id, session_id=session_id)
        except ChatSessionNotFound as error:
            raise ConversationError("conversation.session_not_found") from error
        profile_id = session.search_profile_id
        profile_name: str | None = None
        radar_filters: dict[str, dict[str, object]] = {}
        if profile_id is not None:
            try:
                profile = self.radar.get_profile(
                    owner_id=user_id, profile_id=profile_id
                )
                profile_name = profile.name
                if profile.zones:
                    radar_filters["zones"] = {"zones": list(profile.zones)}
                if profile.budget_max is not None:
                    radar_filters["budget_max"] = {"value": profile.budget_max}
                if profile.min_rooms is not None:
                    radar_filters["min_rooms"] = {"value": profile.min_rooms}
            except Exception:  # noqa: BLE001 - radar unreadable degrades to unbound
                profile_id = None
        pending = self.pending.active_for_session(
            user_id=user_id,
            session_id=session_id,
            profile_id=profile_id,
        )
        return ConversationTurnContext(
            user_id=user_id,
            session_id=session_id,
            verified_profile_id=profile_id,
            profile_name=profile_name,
            pending_action=pending,
            radar_filters=radar_filters,
            correlation_id=correlation_id,
        )


class ServiceEffectApplier:
    """Applies safe durable effects through the explicit application services."""

    def __init__(
        self,
        *,
        services: CopilotServices,
        clock: Clock,
        radar_name: str = "Mi búsqueda",
    ) -> None:
        self.services = services
        self.clock = clock
        self.radar_name = radar_name

    def apply(
        self,
        *,
        effect: TurnEffect,
        context: ConversationTurnContext,
        correlation_id: UUID,
    ) -> TurnEffect:
        if effect.effect_key == "radar.created":
            return self._create_radar(effect, context, correlation_id)
        if effect.effect_key == "filter.set":
            return self._apply_filter(effect, context, correlation_id)
        if effect.effect_key == "filter.cleared":
            return self._apply_filter(effect, context, correlation_id)
        if effect.effect_key in {
            "preference.remembered",
            "preference.revised",
            "preference.withdrawn",
        }:
            return self._apply_preference(effect, context, correlation_id)
        return effect

    def _create_radar(
        self,
        effect: TurnEffect,
        context: ConversationTurnContext,
        correlation_id: UUID,
    ) -> TurnEffect:
        profile, _run = self.services.radar.create_profile(
            owner_id=context.user_id,
            name=self.radar_name,
            zones=(),
            budget_max=None,
            budget_min=None,
            min_rooms=None,
            surface_min=None,
            surface_max=None,
            unknown_strategy=None,
            correlation_id=correlation_id,
        )
        # The durable radar must be the source of truth for the session
        # (FR-003): bind it so the next turn resolves the verified context.
        self.services.chat.bind_profile(
            user_id=context.user_id,
            session_id=context.session_id,
            search_profile_id=profile.profile_id,
            correlation_id=correlation_id,
        )
        return _with_object(effect, "radar", profile.profile_id)

    def _apply_preference(
        self,
        effect: TurnEffect,
        context: ConversationTurnContext,
        correlation_id: UUID,
    ) -> TurnEffect:
        services = self.services
        if services.preferences is None:
            return _rejected(effect, "preferences.not_configured")
        profile_id = context.verified_profile_id
        if profile_id is None:
            return _rejected(effect, "radar.not_bound")
        detail = dict(effect.detail)
        subject_key = detail.get("subject_key")
        if not isinstance(subject_key, str) or not subject_key:
            return _rejected(effect, "preference.missing_subject_key")

        preferences = services.preferences
        if effect.effect_key == "preference.withdrawn":
            expression_id = _active_expression_id_for_subject(
                preferences, profile_id, subject_key
            )
            if expression_id is None:
                return _rejected(effect, "preference.not_active")
            change = preferences.withdraw_expression(
                profile_id=profile_id,
                expression_id=expression_id,
                correlation_id=correlation_id,
            )
            return _with_expression(
                effect,
                "preference",
                _expression_id(change),
            )
        if effect.effect_key == "preference.revised":
            previous_id = _active_expression_id_for_subject(
                preferences, profile_id, subject_key
            )
            if previous_id is None:
                return _rejected(effect, "preference.not_active")
            change = preferences.revise_expression(
                profile_id=profile_id,
                previous_expression_id=previous_id,
                source_message_id=None,
                raw_text=str(
                    detail.get("text") or detail.get("raw_text") or subject_key
                ),
                authority="explicit",
                binding_drafts=(BindingDraft.unresolved("no_structured_evidence"),),
                correlation_id=correlation_id,
            )
            return _with_expression(
                effect,
                "preference",
                _expression_id(change),
            )
        change = preferences.record_expression(
            profile_id=profile_id,
            source_message_id=None,
            subject_key=subject_key,
            raw_text=str(detail.get("text") or detail.get("raw_text") or subject_key),
            authority="explicit",
            binding_drafts=(BindingDraft.unresolved("no_structured_evidence"),),
            correlation_id=correlation_id,
        )
        return _with_expression(
            effect,
            "preference",
            _expression_id(change),
        )

    def _apply_filter(
        self,
        effect: TurnEffect,
        context: ConversationTurnContext,
        correlation_id: UUID,
    ) -> TurnEffect:
        profile_id = context.verified_profile_id
        if profile_id is None:
            return _rejected(effect, "radar.not_bound")
        profile = self.services.radar.get_profile(
            owner_id=context.user_id, profile_id=profile_id
        )
        changes = _filter_changes(effect)
        if not changes:
            return effect
        if effect.status == "pending":
            # Material hard-filter change: persist a durable proposal so the
            # confirmation interrupt can resolve it (FR-013, FR-014).
            proposals = self.services.proposals
            if proposals is None or not hasattr(proposals, "propose"):
                return _rejected(effect, "proposals.not_configured")
            proposal = proposals.propose(
                user_id=context.user_id,
                session_id=context.session_id,
                search_profile_id=profile_id,
                change=changes,
                correlation_id=correlation_id,
            )
            return _with_proposal(effect, proposal)
        updated, _version = self.services.radar.version_profile(
            owner_id=context.user_id,
            profile_id=profile_id,
            expected_version=profile.version,
            changes=changes,
            correlation_id=correlation_id,
        )
        return _with_object(effect, "radar", updated.profile_id)


class RadarRefreshScheduler:
    """Schedules a background radar run; never blocks the chat (FR-025)."""

    def __init__(self, *, radar: RadarService, clock: Clock) -> None:
        self.radar = radar
        self.clock = clock

    def schedule(
        self,
        *,
        profile_id: UUID,
        correlation_id: UUID,
        trigger: str,
    ) -> object | None:
        try:
            latest = self.radar.versions.latest_for_profile(profile_id)
        except Exception:  # noqa: BLE001 - radar unreadable
            return None
        if latest is None:
            return None
        try:
            return self.radar.submit_run(
                profile=self.radar.get_profile(
                    owner_id=_ANY_OWNER, profile_id=profile_id
                ),
                version=latest,
                trigger=trigger,
            )
        except Exception:  # noqa: BLE001 - refresh failure never fails the turn
            return None


class ProposalsPendingReader:
    """Reads the active proposal awaiting confirmation from the proposals store."""

    def __init__(self, *, proposals: SearchProfileUpdateProposals) -> None:
        self.proposals = proposals

    def active_for_session(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        profile_id: UUID | None = None,
    ) -> PendingAction | None:
        if profile_id is None:
            return None
        repository = getattr(self.proposals, "repository", None)
        latest = getattr(repository, "latest_pending_for_profile", None)
        if latest is None:
            return None
        try:
            proposal = latest(profile_id, session_id)
        except Exception:  # noqa: BLE001 - pending store unreadable
            return None
        if proposal is None:
            return None
        return PendingAction(
            kind="profile",
            action_id=str(proposal.proposal_id),
            diff=dict(proposal.diff),
            impact=dict(proposal.impact),
            expires_at=proposal.expires_at,
        )


class ProposalsPendingResolver:
    """Resolves a pending radar change through the proposals service."""

    def __init__(self, *, proposals: SearchProfileUpdateProposals) -> None:
        self.proposals = proposals

    def resolve(
        self,
        *,
        context: ConversationTurnContext,
        decision: Mapping[str, object],
        correlation_id: UUID,
    ) -> tuple[TurnEffect, ...]:
        profile_id = context.verified_profile_id
        action_id = decision.get("action_id")
        if profile_id is None or action_id is None:
            raise ConversationNotReady("profile not bound for resolution")
        decision_kind = decision.get("decision")
        if decision_kind == "approve":
            applied = self.proposals.apply(
                user_id=context.user_id,
                session_id=context.session_id,
                search_profile_id=profile_id,
                proposal_id=UUID(str(action_id)),
                confirmation=True,
                idempotency_key=str(
                    decision.get("idempotency_key") or f"copilot:{action_id}"
                ),
                correlation_id=correlation_id,
            )
            return (
                TurnEffect(
                    effect_key="pending.resolved",
                    act_id="resolve_pending",
                    status="applied",
                    object_type="radar",
                    object_id=str(profile_id),
                    detail={
                        "action_id": str(action_id),
                        "profile_version": applied.profile_version,
                        "run_id": str(applied.run_id) if applied.run_id else None,
                    },
                ),
            )
        if decision_kind == "reject":
            self.proposals.reject(
                user_id=context.user_id,
                session_id=context.session_id,
                search_profile_id=profile_id,
                proposal_id=UUID(str(action_id)),
                note=str(decision.get("reason") or "desde el copilot"),
                correlation_id=correlation_id,
            )
            return (
                TurnEffect(
                    effect_key="pending.rejected",
                    act_id="resolve_pending",
                    status="applied",
                    object_type="radar",
                    object_id=str(profile_id),
                    detail={"action_id": str(action_id)},
                ),
            )
        raise ConversationNotReady(f"unsupported decision: {decision_kind}")


def build_conversation_turn_service(
    *,
    services: CopilotServices,
    proposals: SearchProfileUpdateProposals,
    interpretation: object,
    clock: Clock | None = None,
) -> ConversationTurnService:
    """Compose the turn service over real services and the interpretation seam."""
    clock = clock or (lambda: datetime.now(timezone.utc))
    services_with_proposals = CopilotServices(
        chat=services.chat,
        radar=services.radar,
        preferences=services.preferences,
        proposals=proposals,
    )
    pending_reader = ProposalsPendingReader(proposals=proposals)
    contexts = SessionContextReader(
        chat=services.chat,
        radar=services.radar,
        pending=pending_reader,
        clock=clock,
    )
    return ConversationTurnService(
        contexts=contexts,
        interpretation=_GatewayAdapter(interpretation),
        applier=ServiceEffectApplier(services=services_with_proposals, clock=clock),
        pending=pending_reader,
        pending_resolver=ProposalsPendingResolver(proposals=proposals),
        refresh=RadarRefreshScheduler(radar=services.radar, clock=clock),
        clock=clock,
    )

class _GatewayAdapter:
    """Adapts the InterpretationCompiler to the application InterpretationGateway.

    The compiler exposes ``interpret`` (used by the v4 graph); the turn service
    consumes ``interpret_turn``. Both share the same underlying implementation.
    """

    def __init__(self, compiler: object) -> None:
        self.compiler = compiler

    def interpret_turn(
        self,
        *,
        message_text: str,
        context: ConversationTurnContext,
        correlation_id: object,
    ) -> TurnInterpretation:
        pending = context.pending_action
        compiler = cast(Any, self.compiler)
        result: TurnInterpretation = compiler.interpret(
            message_text=message_text,
            pending_action=(
                {
                    "kind": pending.kind,
                    "action_id": pending.action_id,
                    "diff": dict(pending.diff),
                    "impact": dict(pending.impact),
                }
                if pending is not None
                else None
            ),
            correlation_id=correlation_id,
        )
        return result


def _with_object(effect: TurnEffect, object_type: str, object_id: UUID) -> TurnEffect:
    return TurnEffect(
        effect_key=effect.effect_key,
        act_id=effect.act_id,
        status=effect.status,
        object_type=object_type,
        object_id=str(object_id),
        reason_code=effect.reason_code,
        detail=dict(effect.detail),
    )


def _with_expression(
    effect: TurnEffect, object_type: str, object_id: UUID
) -> TurnEffect:
    return TurnEffect(
        effect_key=effect.effect_key,
        act_id=effect.act_id,
        status="applied",
        object_type=object_type,
        object_id=str(object_id),
        reason_code=effect.reason_code,
        detail=dict(effect.detail),
    )


def _with_proposal(effect: TurnEffect, proposal: object) -> TurnEffect:
    proposal_id = getattr(proposal, "proposal_id", None)
    return TurnEffect(
        effect_key=effect.effect_key,
        act_id=effect.act_id,
        status="pending",
        object_type="proposal",
        object_id=str(proposal_id) if proposal_id is not None else None,
        reason_code="filter.changes_existing_hard_filter",
        detail={
            **dict(effect.detail),
            "proposal_id": str(proposal_id) if proposal_id is not None else "",
        },
    )


def _active_expression_id_for_subject(
    preferences: PreferenceServiceLike,
    profile_id: UUID,
    subject_key: str,
) -> UUID | None:
    try:
        views = preferences.active_view(profile_id)
    except Exception:  # noqa: BLE001 - preference store unreadable
        return None
    for view in views:
        if view.subject_key == subject_key:
            return view.expression_id
    return None


def _expression_id(change: PreferenceChange) -> UUID:
    return change.expression.expression_id


def _rejected(effect: TurnEffect, reason: str) -> TurnEffect:
    return TurnEffect(
        effect_key=effect.effect_key,
        act_id=effect.act_id,
        status="rejected",
        object_type=effect.object_type,
        object_id=effect.object_id,
        reason_code=reason,
        detail=dict(effect.detail),
    )


def _filter_changes(effect: TurnEffect) -> dict[str, object]:
    detail = dict(effect.detail)
    key = detail.get("key")
    if not isinstance(key, str):
        return {}
    if effect.effect_key == "filter.cleared":
        return _clear_change(key)
    value = detail.get("value")
    if key == "zones" and isinstance(value, list):
        return {"zones": [str(item) for item in value]}
    if key == "budget_max" and isinstance(value, (int, float)):
        return {"budget_max": float(value)}
    if key == "min_rooms" and isinstance(value, int):
        return {"min_rooms": int(value)}
    if key == "surface_min" and isinstance(value, (int, float)):
        return {"surface_min": float(value)}
    if key == "surface_max" and isinstance(value, (int, float)):
        return {"surface_max": float(value)}
    return {}


def _clear_change(key: str) -> dict[str, object]:
    if key == "zones":
        return {"zones": []}
    if key == "budget_max":
        return {"budget_max": None}
    if key == "min_rooms":
        return {"min_rooms": None}
    if key == "surface_min":
        return {"surface_min": None}
    if key == "surface_max":
        return {"surface_max": None}
    return {}


_ANY_OWNER = UUID(int=0)
