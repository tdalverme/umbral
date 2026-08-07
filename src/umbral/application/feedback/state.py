"""Pure decision-state rules for feedback events (FR-003/FR-004/FR-005).

A decision change supersedes the active event with a traceable compensation
link; repeating the active action is an idempotent no-op; contacted is a
terminal state that rejects further feedback.
"""
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from umbral.application.feedback.contracts import (
    FeedbackEventType,
    FeedbackTerminal,
    FeedbackValidationError,
    is_event_type,
)

Outcome = Literal["record", "noop"]


@dataclass(frozen=True, slots=True)
class DecisionOutcome:
    """How to treat a new action given the current active event."""

    outcome: Outcome
    superseded: bool


_TERMINAL: FeedbackEventType = "contacted"


def decide(
    current_type: FeedbackEventType | None, new_type: str
) -> DecisionOutcome:
    """Compute the outcome for a new action against the current active type.

    Raises ``FeedbackTerminal`` when the listing is contacted and
    ``FeedbackValidationError`` for unknown event types.
    """

    if not is_event_type(new_type):
        raise FeedbackValidationError((f"feedback.invalid_event_type:{new_type}",))
    typed = _as_type(new_type)
    if current_type == _TERMINAL:
        raise FeedbackTerminal("contacted listings accept no further feedback")
    if current_type is None or current_type == typed:
        return DecisionOutcome(outcome="noop" if current_type is not None else "record", superseded=False)
    return DecisionOutcome(outcome="record", superseded=True)


def _as_type(value: str) -> FeedbackEventType:
    return value  # type: ignore[return-value]
