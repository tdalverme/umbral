"""SQLAlchemy repositories for notifications (H5)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from umbral.application.notifications.contracts import NotificationPreferences
from umbral.infrastructure.db.models.identity import ProductUser
from umbral.infrastructure.db.models.notifications import (
    NotificationDecisionModel,
    NotificationInboxItemModel,
    NotificationPreferencesModel,
)
from umbral.infrastructure.db.models.radar import (
    RecommendationItem,
    RecommendationRun,
    SearchProfile,
)

SessionFactory = Callable[[], Session]


class SqlAlchemyPreferenceRepository:
    """Versioned preferences; every upsert bumps the version."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._factory = session_factory

    def _session(self) -> Session:
        return self._factory()

    def get(
        self, *, user_id: UUID, search_profile_id: UUID
    ) -> NotificationPreferences | None:
        with self._session() as session:
            row = session.execute(
                select(NotificationPreferencesModel).where(
                    NotificationPreferencesModel.user_id == user_id,
                    NotificationPreferencesModel.search_profile_id
                    == search_profile_id,
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return NotificationPreferences(
            email_enabled=row.email_enabled,
            inbox_enabled=row.inbox_enabled,
            timezone=row.timezone,
            quiet_hours_start=row.quiet_hours_start,
            quiet_hours_end=row.quiet_hours_end,
            digest_enabled=row.digest_enabled,
            digest_local_hour=row.digest_local_hour,
            score_threshold=float(row.score_threshold),
            state=row.state,  # type: ignore[arg-type]
            version=row.version,
        )

    def upsert(
        self,
        *,
        user_id: UUID,
        search_profile_id: UUID,
        preferences: NotificationPreferences,
        now: datetime,
        correlation_id: UUID,
    ) -> NotificationPreferences:
        with self._session() as session:
            row = session.execute(
                select(NotificationPreferencesModel).where(
                    NotificationPreferencesModel.user_id == user_id,
                    NotificationPreferencesModel.search_profile_id
                    == search_profile_id,
                )
            ).scalar_one_or_none()
            if row is None:
                row = NotificationPreferencesModel(
                    id=uuid4(),
                    user_id=user_id,
                    search_profile_id=search_profile_id,
                    email_enabled=preferences.email_enabled,
                    inbox_enabled=preferences.inbox_enabled,
                    timezone=preferences.timezone,
                    quiet_hours_start=preferences.quiet_hours_start,
                    quiet_hours_end=preferences.quiet_hours_end,
                    digest_enabled=preferences.digest_enabled,
                    digest_local_hour=preferences.digest_local_hour,
                    score_threshold=preferences.score_threshold,
                    state=preferences.state,
                    version=preferences.version,
                    created_at=now,
                    updated_at=now,
                    source="notifications.preferences.upsert",
                    correlation_id=correlation_id,
                )
                session.add(row)
                session.commit()
                return preferences
            row.email_enabled = preferences.email_enabled
            row.inbox_enabled = preferences.inbox_enabled
            row.timezone = preferences.timezone
            row.quiet_hours_start = preferences.quiet_hours_start
            row.quiet_hours_end = preferences.quiet_hours_end
            row.digest_enabled = preferences.digest_enabled
            row.digest_local_hour = preferences.digest_local_hour
            row.score_threshold = preferences.score_threshold
            row.state = preferences.state
            row.version = preferences.version
            row.updated_at = now
            session.commit()
            return preferences


class SqlAlchemyDecisionRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._factory = session_factory

    def _session(self) -> Session:
        return self._factory()

    def insert(
        self,
        *,
        user_id: UUID,
        search_profile_id: UUID,
        recommendation_item_id: UUID,
        trigger: str,
        reason_code: str,
        decision_state: str,
        policy_version: str,
        preferences_version: int,
        price_before: float | None,
        price_after: float | None,
        duplicate_of_id: UUID | None,
        now: datetime,
        correlation_id: UUID,
    ) -> UUID:
        decision_id = uuid4()
        with self._session() as session:
            session.add(
                NotificationDecisionModel(
                    id=decision_id,
                    user_id=user_id,
                    search_profile_id=search_profile_id,
                    recommendation_item_id=recommendation_item_id,
                    trigger=trigger,
                    reason_code=reason_code,
                    decision_state=decision_state,
                    policy_version=policy_version,
                    preferences_version=preferences_version,
                    price_before=price_before,
                    price_after=price_after,
                    duplicate_of_id=duplicate_of_id,
                    created_at=now,
                    updated_at=now,
                    source="notifications.decision.insert",
                    correlation_id=correlation_id,
                )
            )
            session.commit()
        return decision_id

    def get(self, decision_id: UUID) -> Mapping[str, object] | None:
        with self._session() as session:
            row = session.execute(
                select(NotificationDecisionModel).where(
                    NotificationDecisionModel.id == decision_id
                )
            ).scalar_one_or_none()
        if row is None:
            return None
        return {
            "decision_id": row.id,
            "user_id": row.user_id,
            "search_profile_id": row.search_profile_id,
            "recommendation_item_id": row.recommendation_item_id,
            "trigger": row.trigger,
            "decision_state": row.decision_state,
            "reason_code": row.reason_code,
        }

    def find_by_item_trigger(
        self, *, recommendation_item_id: UUID, trigger: str
    ) -> UUID | None:
        with self._session() as session:
            return session.execute(
                select(NotificationDecisionModel.id).where(
                    NotificationDecisionModel.recommendation_item_id
                    == recommendation_item_id,
                    NotificationDecisionModel.trigger == trigger,
                )
            ).scalar_one_or_none()

    def list_recent(
        self, *, user_id: UUID, search_profile_id: UUID, since: datetime
    ) -> Sequence[Mapping[str, object]]:
        with self._session() as session:
            rows = session.execute(
                select(NotificationDecisionModel).where(
                    NotificationDecisionModel.user_id == user_id,
                    NotificationDecisionModel.search_profile_id == search_profile_id,
                    NotificationDecisionModel.created_at >= since,
                )
            ).scalars()
            return [self._row(row) for row in rows]

    def pending_digest(
        self, *, search_profile_id: UUID
    ) -> Sequence[Mapping[str, object]]:
        with self._session() as session:
            rows = session.execute(
                select(NotificationDecisionModel).where(
                    NotificationDecisionModel.search_profile_id == search_profile_id,
                    NotificationDecisionModel.decision_state == "pending_digest",
                )
            ).scalars()
            return [self._row(row) for row in rows]

    def mark_delivered(
        self, *, decision_id: UUID, provider_message_id: str, now: datetime
    ) -> bool:
        with self._session() as session:
            row = session.execute(
                select(NotificationDecisionModel).where(
                    NotificationDecisionModel.id == decision_id
                )
            ).scalar_one_or_none()
            if row is None or row.decision_state == "delivered":
                return False
            row.decision_state = "delivered"
            row.provider_message_id = provider_message_id
            row.updated_at = now
            session.commit()
            return True

    @staticmethod
    def _row(model: NotificationDecisionModel) -> Mapping[str, object]:
        return {
            "decision_id": model.id,
            "recommendation_item_id": model.recommendation_item_id,
            "trigger": model.trigger,
            "decision_state": model.decision_state,
            "reason_code": model.reason_code,
            "created_at": model.created_at,
        }


class SqlAlchemyInboxRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._factory = session_factory

    def _session(self) -> Session:
        return self._factory()

    def list_for_user(
        self, *, user_id: UUID, limit: int, after: object | None
    ) -> Sequence[Mapping[str, object]]:
        with self._session() as session:
            query = (
                select(NotificationInboxItemModel)
                .where(NotificationInboxItemModel.user_id == user_id)
                .order_by(NotificationInboxItemModel.created_at.desc())
                .limit(limit)
            )
            rows = session.execute(query).scalars()
            return [
                {
                    "decision_id": row.decision_id,
                    "read_at": row.read_at,
                    "acted_at": row.acted_at,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def mark_read(self, *, user_id: UUID, decision_id: UUID, now: datetime) -> bool:
        with self._session() as session:
            row = session.execute(
                select(NotificationInboxItemModel).where(
                    NotificationInboxItemModel.user_id == user_id,
                    NotificationInboxItemModel.decision_id == decision_id,
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            row.read_at = now
            row.updated_at = now
            session.commit()
            return True


class SqlAlchemyProfileReader:
    """Active search profiles and their latest published recommendation items."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._factory = session_factory

    def list_active_profiles(self) -> Sequence[Mapping[str, object]]:
        with self._factory() as session:
            rows = session.execute(
                select(SearchProfile).where(SearchProfile.status == "active")
            ).scalars()
            return [
                {
                    "search_profile_id": row.id,
                    "owner_id": row.owner_id,
                }
                for row in rows
            ]

    def latest_candidates(
        self, *, search_profile_id: UUID
    ) -> Sequence[Mapping[str, object]]:
        with self._factory() as session:
            latest_run = session.execute(
                select(RecommendationRun.id)
                .where(
                    RecommendationRun.profile_id == search_profile_id,
                    RecommendationRun.state == "succeeded",
                )
                .order_by(RecommendationRun.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if latest_run is None:
                return []
            rows = session.execute(
                select(RecommendationItem).where(
                    RecommendationItem.run_id == latest_run
                )
            ).scalars()
            return [
                {
                    "recommendation_item_id": row.id,
                    "listing_id": row.listing_id,
                    "score": float(row.score) if row.score is not None else None,
                    "position": row.position,
                }
                for row in rows
            ]


class SqlAlchemyUserEmailReader:
    """Normalized email of a product user for delivery."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._factory = session_factory

    def email_for(self, user_id: UUID) -> str | None:
        with self._factory() as session:
            return session.execute(
                select(ProductUser.normalized_email).where(ProductUser.id == user_id)
            ).scalar_one_or_none()
