"""Pure signal evaluation for learning proposals (FR-009, US3).

Only like/dislike events with concept-linked reasons count as signals. The
engine is deterministic and LLM-free: it counts consistent signals for a
concept within the policy window and returns a proposal draft when the
threshold is met. Save/dismiss/contacted never produce drafts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from umbral.application.feedback.contracts import LearningPolicyDoc, ProposalDraft


@dataclass(frozen=True, slots=True)
class Signal:
    """One structured learning signal extracted from an active feedback event."""

    event_id: UUID
    concept_key: str
    polarity: str
    created_at: datetime


def evaluate_signals(
    *,
    policy: LearningPolicyDoc,
    concept_key: str,
    polarity: str,
    signals: tuple[Signal, ...],
    now: datetime,
) -> ProposalDraft | None:
    """Return a proposal draft when enough consistent signals are present.

    ``signals`` already contains only concept-linked reasoned like/dislike
    events. The window is applied here so the caller can pass a bounded batch.
    """

    cutoff = now - timedelta(days=policy.window_days)
    consistent = [
        signal.event_id
        for signal in signals
        if signal.concept_key == concept_key
        and signal.polarity == polarity
        and signal.created_at >= cutoff
    ]
    if len(consistent) < policy.min_signals:
        return None
    return ProposalDraft(
        concept_key=concept_key,
        polarity=polarity,
        evidence_event_ids=tuple(consistent),
    )
