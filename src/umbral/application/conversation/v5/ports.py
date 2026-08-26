"""Narrow ports the V5 conversation turn module consumes.

These ports expose only the verified, least-authority reads the turn module
needs. They never expose repository objects or generic query methods.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from umbral.application.conversation.v5.contracts import (
    CommandV5,
    ConversationTurnResultV5,
    ExecutedActV5,
    PendingActionV5,
    TurnContextV5,
    TurnInterpretationV5,
    TurnPlanV5,
)


@dataclass(frozen=True, slots=True)
class FocusedListingV5:
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
    ) -> FocusedListingV5 | None: ...


class PendingActionReaderV5(Protocol):
    def active_for_session(
        self, *, user_id: UUID, session_id: UUID, profile_id: UUID | None
    ) -> PendingActionV5 | None: ...


class ContextReaderV5(Protocol):
    def load(
        self, *, user_id: UUID, session_id: UUID, correlation_id: UUID
    ) -> TurnContextV5: ...


class FeedbackRecorderV5(Protocol):
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


class InterpreterV5(Protocol):
    def interpret(
        self,
        *,
        message_text: str,
        context: TurnContextV5,
        correlation_id: object | None = None,
    ) -> TurnInterpretationV5: ...


class TurnPolicyV5(Protocol):
    def __call__(
        self,
        *,
        user_message: str,
        context: TurnContextV5,
        interpretation: TurnInterpretationV5,
    ) -> TurnPlanV5: ...


class EffectExecutorV5Like(Protocol):
    def execute(
        self,
        *,
        command: CommandV5,
        context: TurnContextV5,
        idempotency_key: str,
    ) -> ExecutedActV5: ...


class PendingResolverV5(Protocol):
    def resolve(
        self,
        *,
        act_id: str,
        context: TurnContextV5,
        pending_ref: str,
        decision: str,
        correlation_id: UUID,
        idempotency_key: str,
    ) -> ExecutedActV5: ...


class TurnAuditWriterV5(Protocol):
    def record(
        self,
        result: ConversationTurnResultV5,
        versions: Mapping[str, object],
    ) -> None: ...
