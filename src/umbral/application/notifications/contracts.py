"""Pure values and contracts for proactive notifications (H5).

The planner, preferences and policy live here without any infrastructure
dependency (Principle III). Reason codes and decision states are the
machine-checkable vocabulary of the golden dataset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import Literal
from uuid import UUID

DecisionState = Literal[
    "pending_delivery",
    "pending_digest",
    "postponed",
    "duplicated",
    "discarded",
    "delivered",
    "read",
    "acted",
]

Trigger = Literal["new_match", "price_drop"]

_REASON_CODES: frozenset[str] = frozenset(
    {
        "new_match",
        "price_drop",
        "duplicate",
        "quiet_hours",
        "fatigue",
        "digest",
        "digest_disabled",
        "preferences_disabled",
        "preferences_paused",
        "no_channels",
    }
)


@dataclass(frozen=True, slots=True)
class NotificationCandidate:
    """One recommendation item evaluated by the planner."""

    recommendation_item_id: UUID
    search_profile_id: UUID
    trigger: Trigger
    score: float | None = None
    price_before: float | None = None
    price_after: float | None = None
    published_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class HistoryDecision:
    """A prior decision used for dedupe and fatigue."""

    decision_id: UUID
    recommendation_item_id: UUID
    trigger: Trigger
    decision_state: str
    delivered_at: datetime | None = None
    viewed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class NotificationPreferences:
    """Versioned per-user/per-search notification preferences."""

    email_enabled: bool = True
    inbox_enabled: bool = True
    timezone: str = "America/Argentina/Buenos_Aires"
    quiet_hours_start: time = field(default_factory=lambda: time(22, 0))
    quiet_hours_end: time = field(default_factory=lambda: time(8, 0))
    digest_enabled: bool = True
    digest_local_hour: int = 9
    score_threshold: float = 0.6
    state: Literal["active", "paused", "disabled"] = "active"
    version: int = 1


@dataclass(frozen=True, slots=True)
class NotificationPolicy:
    """Versioned, immutable notification policy (contract file)."""

    immediate_score_threshold: float = 0.75
    fatigue_cooldown_hours: float = 6.0
    fatigue_window_hours: float = 24.0
    digest_default_local_hour: int = 9
    digest_max_items: int = 10
    quiet_hours_start: time = field(default_factory=lambda: time(22, 0))
    quiet_hours_end: time = field(default_factory=lambda: time(8, 0))


@dataclass(frozen=True, slots=True)
class PlannerDecision:
    """One decision produced by the deterministic planner."""

    recommendation_item_id: UUID
    search_profile_id: UUID
    trigger: Trigger
    reason_code: str
    decision_state: DecisionState
    duplicate_of_id: UUID | None = None


class PlannerValidationError(ValueError):
    """A golden case or planner input violates its declared shape."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"notifications_planner_invalid: {reason}")
