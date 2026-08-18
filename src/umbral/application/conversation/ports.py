"""Ports consumed by the conversational copilot turn orchestrator.

Every mutation goes through an explicit application service; this module only
declares the seams the orchestrator needs: verified context, ordered
interpretation, durable-effect application and refresh scheduling.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from umbral.application.conversation.contracts import (
    ConversationTurnContext,
    PendingAction,
    TurnEffect,
    TurnInterpretation,
)


class TurnContextReader(Protocol):
    """Loads the verified active context for one chat session."""

    def load(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        correlation_id: UUID,
    ) -> ConversationTurnContext: ...


class InterpretationGateway(Protocol):
    """Produces the ordered multi-act interpretation of one message.

    Only the acts are generative; their planning and routing are deterministic
    (constitution: the model never decides durable state or ranking).
    """

    def interpret_turn(
        self,
        *,
        message_text: str,
        context: ConversationTurnContext,
        correlation_id: UUID,
    ) -> TurnInterpretation: ...


class EffectApplier(Protocol):
    """Applies one planned durable effect through an explicit service.

    Status ``applied`` means the mutation was persisted; ``remembered`` and
    ``rejected`` are reported back for soft/no-evidence or invalid acts.
    ``pending`` effects are never applied here: they await confirmation.
    """

    def apply(
        self,
        *,
        effect: TurnEffect,
        context: ConversationTurnContext,
        correlation_id: UUID,
    ) -> TurnEffect: ...


class PendingActionResolver(Protocol):
    """Resolves a durable action awaiting confirmation (explicit service)."""

    def resolve(
        self,
        *,
        context: ConversationTurnContext,
        decision: Mapping[str, object],
        correlation_id: UUID,
    ) -> tuple[TurnEffect, ...]: ...


class PendingActionReader(Protocol):
    """Reads the active pending action for a session, if any."""

    def active_for_session(
        self, *, user_id: UUID, session_id: UUID, profile_id: UUID | None = None
    ) -> PendingAction | None: ...


class RefreshScheduler(Protocol):
    """Requests a background refresh of a radar version (never blocks chat)."""

    def schedule(
        self,
        *,
        profile_id: UUID,
        correlation_id: UUID,
        trigger: str,
    ) -> object | None: ...


class TurnTelemetry(Protocol):
    """Records durable, auditable traces of turn application."""

    def record_turn(
        self,
        *,
        session_id: UUID,
        run_id: UUID,
        interpretation: TurnInterpretation,
        effects: tuple[TurnEffect, ...],
        correlation_id: UUID,
    ) -> None: ...