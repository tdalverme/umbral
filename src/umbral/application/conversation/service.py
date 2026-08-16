"""Conversational copilot turn orchestrator.

``ConversationTurnService`` is the single application seam for a chat turn:
it loads the verified context, asks the interpretation gateway for ordered
multi-acts, plans deterministic effects, applies only the safe/reversible ones
through explicit services and reports the routing decision (refresh and/or
confirmation) to the agent graph. The model never decides durable state,
hard filters or ranking (constitution).

The service exposes granular steps (``load_context``, ``interpret``, ``plan``,
``apply_safe``) so the v4 agent graph can interrupt for confirmation between
steps; ``process_turn`` composes them for the atomic happy path.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

from umbral.application.conversation.contracts import (
    ConversationError,
    ConversationNotReady,
    ConversationTurnContext,
    ConversationTurnResult,
    PendingAction,
    TurnEffect,
    TurnInterpretation,
)
from umbral.application.conversation.policy import TurnPlan, plan_turn
from umbral.application.conversation.ports import (
    EffectApplier,
    InterpretationGateway,
    PendingActionReader,
    PendingActionResolver,
    RefreshScheduler,
    TurnContextReader,
)

Clock = Callable[[], datetime]


class ConversationTurnService:
    """Orchestrates one conversational turn with no generative authority."""

    def __init__(
        self,
        *,
        contexts: TurnContextReader,
        interpretation: InterpretationGateway,
        applier: EffectApplier,
        pending: PendingActionReader,
        pending_resolver: PendingActionResolver,
        refresh: RefreshScheduler,
        clock: Clock | None = None,
    ) -> None:
        self.contexts = contexts
        self.interpretation = interpretation
        self.applier = applier
        self.pending = pending
        self.pending_resolver = pending_resolver
        self.refresh = refresh
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def load_context(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        correlation_id: UUID,
    ) -> ConversationTurnContext:
        return self.contexts.load(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )

    def interpret(
        self,
        *,
        message_text: str,
        context: ConversationTurnContext,
        correlation_id: UUID,
    ) -> TurnInterpretation:
        return self.interpretation.interpret_turn(
            message_text=message_text,
            context=context,
            correlation_id=correlation_id,
        )

    def plan(
        self,
        *,
        interpretation: TurnInterpretation,
        context: ConversationTurnContext,
    ) -> TurnPlan:
        return plan_turn(interpretation=interpretation, context=context)

    def apply_safe(
        self,
        *,
        plan: TurnPlan,
        context: ConversationTurnContext,
        correlation_id: UUID,
    ) -> tuple[tuple[TurnEffect, ...], tuple[Mapping[str, object], ...]]:
        applied: list[TurnEffect] = []
        active_context = context
        for effect in plan.effects:
            try:
                applied.append(
                    self.applier.apply(
                        effect=effect,
                        context=active_context,
                        correlation_id=correlation_id,
                    )
                )
            except ConversationError as error:
                applied.append(
                    replace(
                        effect,
                        status="rejected",
                        reason_code=str(error.code or "conversation.apply_failed"),
                    )
                )
            except Exception as error:
                applied.append(
                    replace(
                        effect,
                        status="rejected",
                        reason_code=f"conversation.apply_failed:{type(error).__name__}",
                    )
                )
            # An act may have created and bound the radar (FR-003); later acts
            # of the same turn must see the verified profile (FR-004).
            if active_context.verified_profile_id is None:
                active_context = self.contexts.load(
                    user_id=context.user_id,
                    session_id=context.session_id,
                    correlation_id=correlation_id,
                )
        return tuple(applied), ()

    def schedule_refresh(
        self,
        *,
        context: ConversationTurnContext,
        correlation_id: UUID,
    ) -> tuple[Mapping[str, object], ...]:
        if context.verified_profile_id is None:
            return ()
        scheduled = self.refresh.schedule(
            profile_id=context.verified_profile_id,
            correlation_id=correlation_id,
            trigger="conversational_turn",
        )
        if scheduled is None:
            return ()
        return (
            {
                "object_type": "radar",
                "object_id": str(context.verified_profile_id),
                "run_id": str(getattr(scheduled, "run_id", "")),
            },
        )

    def process_turn(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        message_text: str,
        correlation_id: UUID,
    ) -> ConversationTurnResult:
        context = self.load_context(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        interpretation = self.interpret(
            message_text=message_text,
            context=context,
            correlation_id=correlation_id,
        )
        plan = self.plan(interpretation=interpretation, context=context)
        effects, _refreshed = self.apply_safe(
            plan=plan,
            context=context,
            correlation_id=correlation_id,
        )
        refreshed: tuple[Mapping[str, object], ...] = ()
        if (
            plan.routing.refresh_required
            and not plan.routing.confirmation_required
        ):
            refreshed = self.schedule_refresh(
                context=context,
                correlation_id=correlation_id,
            )
        return ConversationTurnResult(
            effects=effects,
            routing=plan.routing,
            refreshed_objects=refreshed,
            question=plan.question,
        )

    def resolve(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        decision: Mapping[str, object],
        correlation_id: UUID,
    ) -> tuple[TurnEffect, ...]:
        """Resolve the awaited pending action through its explicit service."""
        context = self.contexts.load(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        pending = self.pending.active_for_session(
            user_id=user_id,
            session_id=session_id,
            profile_id=context.verified_profile_id,
        )
        if pending is None:
            raise ConversationNotReady("pending action not found")
        decision_with_pending = dict(decision)
        decision_with_pending.setdefault("action_id", pending.action_id)
        decision_with_pending.setdefault("kind", pending.kind)
        return self.pending_resolver.resolve(
            context=context,
            decision=decision_with_pending,
            correlation_id=correlation_id,
        )

    def active_pending(
        self, *, user_id: UUID, session_id: UUID
    ) -> PendingAction | None:
        return self.pending.active_for_session(user_id=user_id, session_id=session_id)

    def hydrate_pending(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        pending: PendingAction,
        correlation_id: UUID,
    ) -> ConversationTurnContext:
        context = self.contexts.load(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        return replace(context, pending_action=pending)