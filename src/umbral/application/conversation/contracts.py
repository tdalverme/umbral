"""Pure values and errors for the conversational copilot turn orchestrator.

The orchestrator is the durable seam between the chat and the explicit
mutation services: it loads verified context, plans deterministic effects from
ordered multi-acts and decides routing (refresh / confirmation) without the
model deciding ranking, hard filters or durable state (constitution).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

ActKind = Literal[
    "resolve_pending",
    "create_radar",
    "set_filter",
    "clear_filter",
    "express_preference",
    "revise_preference",
    "withdraw_preference",
    "record_feedback",
    "query",
]

EffectStatus = Literal["applied", "pending", "remembered", "rejected"]

KNOWN_ACT_KINDS: frozenset[str] = frozenset(
    {
        "resolve_pending",
        "create_radar",
        "set_filter",
        "clear_filter",
        "express_preference",
        "revise_preference",
        "withdraw_preference",
        "record_feedback",
        "query",
    }
)


@dataclass(frozen=True, slots=True)
class ConversationAct:
    """One ordered act of a validated conversation interpretation."""

    act_id: str
    kind: str
    target: Mapping[str, str] = field(default_factory=dict)
    payload: Mapping[str, object] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class TurnInterpretation:
    """Validated multi-act interpretation of one user message."""

    acts: tuple[ConversationAct, ...]
    ambiguity: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class TurnEffect:
    """A planned or applied durable effect with its public status."""

    effect_key: str
    act_id: str
    status: EffectStatus
    object_type: str | None = None
    object_id: str | None = None
    reason_code: str | None = None
    detail: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """Deterministic branch after safe effects: refresh and/or confirmation."""

    refresh_required: bool
    confirmation_required: bool


def resolve_routing(
    *,
    refresh_required: bool,
    confirmation_required: bool,
) -> RoutingDecision:
    return RoutingDecision(
        refresh_required=refresh_required,
        confirmation_required=confirmation_required,
    )


@dataclass(frozen=True, slots=True)
class PendingAction:
    """A durable action awaiting confirmation."""

    kind: str
    action_id: str
    diff: Mapping[str, object] = field(default_factory=dict)
    impact: Mapping[str, object] = field(default_factory=dict)
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ConversationTurnContext:
    """The verified active context used to interpret the next message.

    ``verified_profile_id`` is the durable radar bound to the session after
    context loading; ``radar_filters`` mirrors the current hard-filter snapshot
    used only to decide the deterministic routing of this turn.
    """

    user_id: UUID
    session_id: UUID
    verified_profile_id: UUID | None = None
    profile_name: str | None = None
    pending_action: PendingAction | None = None
    answered_slots: tuple[str, ...] = ()
    radar_filters: Mapping[str, Mapping[str, object]] = field(default_factory=dict)
    correlation_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ConversationTurnResult:
    """Outcome of one turn: durable effects, routing and reply inputs."""

    effects: tuple[TurnEffect, ...]
    routing: RoutingDecision
    refreshed_objects: tuple[Mapping[str, object], ...] = field(default_factory=tuple)
    question: str | None = None
    reply_inputs: Mapping[str, object] = field(default_factory=dict)


class ConversationError(Exception):
    """Base class for sanitized copilot turn failures."""

    code = "conversation.error"


class ConversationNotReady(ConversationError):
    """A pre-condition of the active context is missing or invalid."""

    code = "conversation.not_ready"


class ConversationInterpretationFailed(ConversationError):
    """The interpretation gateway did not produce a usable multi-act payload."""

    code = "conversation.interpretation_failed"


class ConversationContradiction(ConversationError):
    """Two acts of the same turn contradict each other materially."""

    code = "conversation.contradiction"


def is_known_act_kind(value: str) -> bool:
    return value in KNOWN_ACT_KINDS