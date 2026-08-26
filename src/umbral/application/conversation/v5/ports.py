"""Narrow ports the V5 conversation turn module consumes.

These ports expose only the verified, least-authority reads the turn module
needs. They never expose repository objects or generic query methods.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from umbral.application.conversation.v5.contracts import (
    PendingActionV5,
    TurnContextV5,
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


class ContextAssemblyFailed(Exception):
    """The authorized context could not be assembled for a typed reason."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
