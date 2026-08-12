"""Planner service: scan published items, decide and persist (H5, UM-H5-003..).

The plan duty reads the latest published recommendation run items of each
active search profile, runs the deterministic planner and persists decisions
(idempotent by item+trigger). The digest duty materializes pending_digest
decisions into delivery.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from umbral.application.notifications.contracts import (
    HistoryDecision,
    NotificationCandidate,
    NotificationPolicy,
)
from umbral.application.notifications.decision_service import DecisionService
from umbral.application.notifications.planner import plan
from umbral.application.notifications.ports import (
    DecisionRepository,
    ProfileNotificationReader,
)
from umbral.application.notifications.preferences_service import PreferencesService

_TRIGGER_NEW_MATCH = "new_match"

# Window for prior decisions considered by dedupe/fatigue. A decision made
# weeks ago must still block a re-notification of the same item+trigger.
_HISTORY_WINDOW_DAYS = 90


class PlannerService:
    """Scans new items, plans and records decisions for active profiles."""

    def __init__(
        self,
        *,
        decisions: DecisionRepository,
        decision_service: DecisionService,
        preferences: PreferencesService,
        profiles: ProfileNotificationReader,
        delivery: object,
        policy: NotificationPolicy,
    ) -> None:
        self._decisions = decisions
        self._decision_service = decision_service
        self._preferences = preferences
        self._profiles = profiles
        self._delivery = delivery
        self._policy = policy

    def plan_all(self, *, now: datetime) -> int:
        correlation_id = uuid4()
        recorded = 0
        for profile in self._profiles.list_active_profiles():
            search_profile_id = UUID(str(profile["search_profile_id"]))
            owner_id = UUID(str(profile["owner_id"]))
            candidates = self._candidates(search_profile_id)
            if not candidates:
                continue
            recorded += self.plan_profile(
                user_id=owner_id,
                search_profile_id=search_profile_id,
                candidates=candidates,
                now=now,
                correlation_id=correlation_id,
            )
        return recorded

    def digest_all(self, *, now: datetime) -> int:
        correlation_id = uuid4()
        materialized = 0
        for profile in self._profiles.list_active_profiles():
            search_profile_id = UUID(str(profile["search_profile_id"]))
            pending = self._decisions.pending_digest(
                search_profile_id=search_profile_id
            )
            for item in pending:
                decision_id = item.get("decision_id")
                if not isinstance(decision_id, UUID):
                    continue
                delivered = self._delivery.deliver_decision(  # type: ignore[attr-defined]
                    decision_id=decision_id,
                    now=now,
                    correlation_id=correlation_id,
                )
                if delivered:
                    materialized += 1
        return materialized

    def _candidates(
        self, search_profile_id: UUID
    ) -> tuple[NotificationCandidate, ...]:
        candidates: list[NotificationCandidate] = []
        for item in self._profiles.latest_candidates(
            search_profile_id=search_profile_id
        ):
            candidates.append(
                NotificationCandidate(
                    recommendation_item_id=UUID(str(item["recommendation_item_id"])),
                    search_profile_id=search_profile_id,
                    trigger="new_match",
                    score=_optional_float(item.get("score")),
                    published_at=datetime.now(timezone.utc),
                )
            )
        return tuple(candidates)

    def plan_profile(
        self,
        *,
        user_id: UUID,
        search_profile_id: UUID,
        candidates: Sequence[NotificationCandidate],
        now: datetime,
        correlation_id: UUID,
    ) -> int:
        prefs = self._preferences.get(
            user_id=user_id, search_profile_id=search_profile_id
        )
        if prefs.state == "disabled":
            return 0
        history = self._decisions.list_recent(
            user_id=user_id,
            search_profile_id=search_profile_id,
            since=now - timedelta(days=_HISTORY_WINDOW_DAYS),
        )
        history_decisions = tuple(
            HistoryDecision(
                decision_id=UUID(str(item["decision_id"])),
                recommendation_item_id=UUID(str(item["recommendation_item_id"])),
                trigger=str(item["trigger"]),  # type: ignore[arg-type]
                decision_state=str(item["decision_state"]),
                delivered_at=None,
                viewed_at=None,
            )
            for item in history
        )
        recorded = 0
        for candidate in candidates:
            decision = plan(
                candidate=candidate,
                history=history_decisions,
                preferences=prefs,
                policy=self._policy,
                now=now,
            )
            if decision.decision_state in {"duplicated", "discarded"}:
                continue
            self._decision_service.record(
                user_id=user_id,
                search_profile_id=search_profile_id,
                decision=decision,
                inbox_enabled=prefs.inbox_enabled,
                now=now,
                correlation_id=correlation_id,
            )
            recorded += 1
        return recorded

    def digest_profile(
        self,
        *,
        user_id: UUID,
        search_profile_id: UUID,
        now: datetime,
        correlation_id: UUID,
    ) -> int:
        pending = self._decisions.pending_digest(search_profile_id=search_profile_id)
        return len(pending)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
