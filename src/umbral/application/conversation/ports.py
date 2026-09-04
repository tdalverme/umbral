"""Narrow ports the V5 conversation turn module consumes.

These ports expose only the verified, least-authority reads the turn module
needs. They never expose repository objects or generic query methods.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from umbral.application.conversation.contracts import (
    Command,
    ConversationTurnResult,
    ExecutedAct,
    PendingAction,
    TurnContext,
    TurnInterpretation,
    TurnPlan,
)


@dataclass(frozen=True, slots=True)
class FocusedListing:
    """A listing the user is viewing, already verified as accessible.

    The listing document text is carried as untrusted data so the context can
    keep it separate from the user-authored message.
    """

    listing_id: UUID
    text: str

    @property
    def entity_ref(self) -> str:
        return f"listing:{self.listing_id}"


class FocusedEntityReader(Protocol):
    def verified_focus(
        self, *, user_id: UUID, session_id: UUID
    ) -> FocusedListing | None: ...


class PendingActionReader(Protocol):
    def active_for_session(
        self, *, user_id: UUID, session_id: UUID, profile_id: UUID | None
    ) -> PendingAction | None: ...


class ContextReader(Protocol):
    def load(
        self, *, user_id: UUID, session_id: UUID, correlation_id: UUID
    ) -> TurnContext: ...


class FeedbackRecorder(Protocol):
    """The existing feedback application interface used by feedback tooling."""

    def record_feedback(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        listing_id: UUID,
        run_id: UUID | None,
        event_type: str,
        reason_keys: tuple[str, ...],
        idempotency_key: str,
        correlation_id: UUID,
        concept_feedback: tuple[Mapping[str, object], ...] = (),
        free_feedback: str | None = None,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> object: ...


class ContextAssemblyFailed(Exception):
    """The authorized context could not be assembled for a typed reason."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class Interpreter(Protocol):
    def interpret(
        self,
        *,
        message_text: str,
        context: TurnContext,
        correlation_id: object | None = None,
    ) -> TurnInterpretation: ...


class TurnPolicy(Protocol):
    def __call__(
        self,
        *,
        user_message: str,
        context: TurnContext,
        interpretation: TurnInterpretation,
    ) -> TurnPlan: ...


class EffectExecutorLike(Protocol):
    def execute(
        self,
        *,
        command: Command,
        context: TurnContext,
        idempotency_key: str,
    ) -> ExecutedAct: ...


class PendingResolver(Protocol):
    def resolve(
        self,
        *,
        act_id: str,
        context: TurnContext,
        pending_ref: str,
        decision: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> ExecutedAct: ...


class TurnAuditWriter(Protocol):
    def record(
        self,
        result: ConversationTurnResult,
        versions: Mapping[str, object],
    ) -> None: ...
