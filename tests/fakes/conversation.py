"""In-memory adapters for the conversational copilot test seam."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from umbral.application.conversation.contracts import (
    ConversationTurnContext,
    PendingAction,
    TurnEffect,
    TurnInterpretation,
)


@dataclass
class FakeTurnContextReader:
    """Serves a fixed verified context per session."""

    context: ConversationTurnContext | None = None

    def load(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        correlation_id: UUID,
    ) -> ConversationTurnContext:
        if self.context is not None:
            return self.context
        return ConversationTurnContext(user_id=user_id, session_id=session_id)


@dataclass
class FakeInterpretationGateway:
    """Returns a scripted multi-act interpretation or a one-act default."""

    interpretation: TurnInterpretation | None = None
    calls: list[str] = field(default_factory=list)

    def interpret_turn(
        self,
        *,
        message_text: str,
        context: ConversationTurnContext,
        correlation_id: UUID,
    ) -> TurnInterpretation:
        self.calls.append(message_text)
        if self.interpretation is not None:
            return self.interpretation
        return TurnInterpretation(acts=())


@dataclass
class FakeEffectApplier:
    """Records every applied effect and reports success."""

    applied: list[TurnEffect] = field(default_factory=list)
    fail_effect_key: str | None = None

    def apply(
        self,
        *,
        effect: TurnEffect,
        context: ConversationTurnContext,
        correlation_id: UUID,
    ) -> TurnEffect:
        if effect.effect_key == self.fail_effect_key:
            raise RuntimeError("injected effect failure")
        self.applied.append(effect)
        return effect


@dataclass
class FakePendingActionReader:
    """Returns a scripted pending action for a session."""

    pending: PendingAction | None = None

    def active_for_session(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        profile_id: UUID | None = None,
    ) -> PendingAction | None:
        return self.pending


@dataclass
class FakePendingActionResolver:
    """Records resolution decisions and emits scripted effects."""

    decisions: list[dict[str, object]] = field(default_factory=list)
    effects: tuple[TurnEffect, ...] = ()

    def resolve(
        self,
        *,
        context: ConversationTurnContext,
        decision: Mapping[str, object],
        correlation_id: UUID,
    ) -> tuple[TurnEffect, ...]:
        self.decisions.append(dict(decision))
        if self.effects:
            return self.effects
        return (
            TurnEffect(
                effect_key="pending.resolved",
                act_id="resolve",
                status="applied",
                detail=dict(decision),
            ),
        )


@dataclass
class FakeRefreshScheduler:
    """Remembers refresh calls; returns a fake run object."""

    scheduled: list[dict[str, object]] = field(default_factory=list)

    def schedule(
        self, *, profile_id: UUID, correlation_id: UUID, trigger: str
    ) -> object | None:
        run_id = uuid4()
        self.scheduled.append(
            {
                "profile_id": profile_id,
                "correlation_id": correlation_id,
                "trigger": trigger,
                "run_id": run_id,
            }
        )
        return FakeRun(run_id)


class FakeRun:
    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id