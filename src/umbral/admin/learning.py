"""Learning-oriented internal admin metrics."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any

from umbral.database.repositories import BaseRepository

DEFAULT_WINDOW_DAYS = 14
MAX_ANALYTICS_ROWS = 2000


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _in_window(row: dict, field: str, since: datetime) -> bool:
    value = _parse_dt(row.get(field))
    return value is not None and value >= since


def _pct(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator) * 100, 1)


def _avg(values: list[int | float]) -> float:
    return round(float(mean(values)), 1) if values else 0.0


def _reason_label(reason: str | None) -> str:
    labels = {
        "good_location": "Buena zona",
        "good_price": "Buen precio",
        "key_feature": "Tiene algo clave",
        "good_vibe": "Buena vibra",
        "contact_visit": "Contactar/visitar",
        "too_expensive": "Muy caro",
        "bad_location": "Zona",
        "too_small": "Muy chico",
        "missing_key_feature": "Falta algo clave",
        "style_condition": "Estado/estilo",
        "already_seen": "Ya lo vi",
    }
    if not reason:
        return "Sin motivo"
    return labels.get(reason, reason.replace("_", " ").capitalize())


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


class AdminLearningRepository(BaseRepository):
    """Read-only Supabase queries used by the internal learning dashboard."""

    def snapshot(self, *, window_days: int = DEFAULT_WINDOW_DAYS) -> dict[str, Any]:
        since = _utc_now() - timedelta(days=window_days)
        return {
            "counts": {
                "raw_listings": self._count("raw_listings"),
                "analyzed_listings": self._count("analyzed_listings"),
                "active_analyzed_listings": self._count(
                    "analyzed_listings",
                    eq={"is_active": True},
                ),
            },
            "users": self._rows(
                "users",
                "id, telegram_id, telegram_username, is_active, onboarding_completed, "
                "onboarding_step, total_likes, total_dislikes, preferences, created_at, updated_at",
                order_by="created_at",
            ),
            "notifications": self._rows(
                "sent_notifications",
                "id, user_id, analyzed_listing_id, final_score, sent_at",
                order_by="sent_at",
            ),
            "feedback": self._rows(
                "user_feedback",
                "id, user_id, analyzed_listing_id, feedback_type, reason, metadata, created_at, "
                "analyzed_listings(neighborhood, rooms, price_usd, executive_summary, "
                "raw_listings(title, url, operation_type))",
                order_by="created_at",
            ),
            "matches": self._rows(
                "user_listing_matches",
                "id, user_id, analyzed_listing_id, final_score, band, gaps, computed_at, "
                "notified_at, liked_at, dismissed_at",
                order_by="computed_at",
            ),
            "ingestion_events": self._rows(
                "ingestion_events",
                "id, source, status, quality_score, reason, tags, created_at",
                order_by="created_at",
                gte={"created_at": since.isoformat()},
            ),
        }

    def _count(self, table: str, *, eq: dict[str, Any] | None = None) -> int:
        query = self.client.table(table).select("id", count="exact")
        for field, value in (eq or {}).items():
            query = query.eq(field, value)
        response = query.execute()
        if getattr(response, "count", None) is not None:
            return int(response.count)
        return len(response.data or [])

    def _rows(
        self,
        table: str,
        columns: str,
        *,
        order_by: str | None = None,
        gte: dict[str, Any] | None = None,
        limit: int = MAX_ANALYTICS_ROWS,
    ) -> list[dict]:
        query = self.client.table(table).select(columns)
        for field, value in (gte or {}).items():
            query = query.gte(field, value)
        if order_by:
            query = query.order(order_by, desc=True)
        response = query.limit(limit).execute()
        return response.data or []


class AdminLearningDashboard:
    """Builds the learning dashboard payload from repository snapshots."""

    def __init__(self, repository: AdminLearningRepository | None = None):
        self.repository = repository or AdminLearningRepository()

    def build(self, *, window_days: int = DEFAULT_WINDOW_DAYS) -> dict[str, Any]:
        snapshot = self.repository.snapshot(window_days=window_days)
        since = _utc_now() - timedelta(days=window_days)

        users = snapshot["users"]
        notifications = snapshot["notifications"]
        feedback = snapshot["feedback"]
        matches = snapshot["matches"]
        ingestion_events = snapshot["ingestion_events"]
        counts = snapshot["counts"]

        recent_notifications = [row for row in notifications if _in_window(row, "sent_at", since)]
        recent_feedback = [row for row in feedback if _in_window(row, "created_at", since)]
        recent_matches = [row for row in matches if _in_window(row, "computed_at", since)]

        return {
            "generated_at": _utc_now().isoformat(),
            "window_days": window_days,
            "summary": self._summary(
                counts=counts,
                users=users,
                notifications=notifications,
                recent_notifications=recent_notifications,
                feedback=feedback,
                recent_feedback=recent_feedback,
                matches=matches,
                recent_matches=recent_matches,
                ingestion_events=ingestion_events,
            ),
            "feedback_reasons": self._feedback_reasons(recent_feedback),
            "users": self._users(users, notifications, feedback),
            "match_quality": self._match_quality(recent_matches),
            "source_quality": self._source_quality(ingestion_events),
            "recent_feedback": self._recent_feedback(recent_feedback[:20]),
            "learning_questions": self._learning_questions(
                users=users,
                recent_notifications=recent_notifications,
                recent_feedback=recent_feedback,
                ingestion_events=ingestion_events,
            ),
        }

    def _summary(
        self,
        *,
        counts: dict[str, int],
        users: list[dict],
        notifications: list[dict],
        recent_notifications: list[dict],
        feedback: list[dict],
        recent_feedback: list[dict],
        matches: list[dict],
        recent_matches: list[dict],
        ingestion_events: list[dict],
    ) -> dict[str, Any]:
        active_users = [user for user in users if user.get("is_active") is True]
        onboarded_users = [user for user in users if user.get("onboarding_completed") is True]
        likes = [row for row in recent_feedback if row.get("feedback_type") == "like"]
        dislikes = [row for row in recent_feedback if row.get("feedback_type") == "dislike"]
        accepted = [event for event in ingestion_events if event.get("status") == "accepted"]
        rejected = [event for event in ingestion_events if event.get("status") == "rejected"]
        errors = [event for event in ingestion_events if event.get("status") == "error"]

        return {
            "users_total": len(users),
            "users_active": len(active_users),
            "users_onboarded": len(onboarded_users),
            "onboarding_rate_pct": _pct(len(onboarded_users), len(users)),
            "raw_listings_total": counts.get("raw_listings", 0),
            "analyzed_listings_total": counts.get("analyzed_listings", 0),
            "active_listings_total": counts.get("active_analyzed_listings", 0),
            "analysis_coverage_pct": _pct(
                counts.get("analyzed_listings", 0),
                counts.get("raw_listings", 0),
            ),
            "matches_cached_total": len(matches),
            "matches_cached_window": len(recent_matches),
            "avg_match_score_window": _avg(
                [_safe_float(row.get("final_score")) for row in recent_matches]
            ),
            "notifications_sent_total": len(notifications),
            "notifications_sent_window": len(recent_notifications),
            "feedback_total": len(feedback),
            "feedback_window": len(recent_feedback),
            "likes_window": len(likes),
            "dislikes_window": len(dislikes),
            "feedback_response_rate_pct": _pct(len(recent_feedback), len(recent_notifications)),
            "like_rate_pct": _pct(len(likes), len(recent_feedback)),
            "notification_to_like_rate_pct": _pct(len(likes), len(recent_notifications)),
            "ingestion_accepted_window": len(accepted),
            "ingestion_rejected_window": len(rejected),
            "ingestion_errors_window": len(errors),
            "ingestion_acceptance_rate_pct": _pct(len(accepted), len(ingestion_events)),
        }

    def _feedback_reasons(self, feedback: list[dict]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in feedback:
            reason = row.get("reason") or "none"
            bucket = grouped.setdefault(
                reason,
                {
                    "reason": reason,
                    "label": _reason_label(reason if reason != "none" else None),
                    "count": 0,
                    "likes": 0,
                    "dislikes": 0,
                },
            )
            bucket["count"] += 1
            if row.get("feedback_type") == "like":
                bucket["likes"] += 1
            elif row.get("feedback_type") == "dislike":
                bucket["dislikes"] += 1
        return sorted(grouped.values(), key=lambda item: item["count"], reverse=True)

    def _users(
        self,
        users: list[dict],
        notifications: list[dict],
        feedback: list[dict],
    ) -> list[dict[str, Any]]:
        notifications_by_user: Counter[str] = Counter()
        feedback_by_user: Counter[str] = Counter()
        likes_by_user: Counter[str] = Counter()
        dislikes_by_user: Counter[str] = Counter()
        last_notification: dict[str, datetime] = {}
        last_feedback: dict[str, datetime] = {}
        min_dt = datetime.min.replace(tzinfo=timezone.utc)

        for row in notifications:
            user_id = row.get("user_id")
            if not user_id:
                continue
            notifications_by_user[user_id] += 1
            sent_at = _parse_dt(row.get("sent_at"))
            if sent_at and sent_at > last_notification.get(user_id, min_dt):
                last_notification[user_id] = sent_at

        for row in feedback:
            user_id = row.get("user_id")
            if not user_id:
                continue
            feedback_by_user[user_id] += 1
            if row.get("feedback_type") == "like":
                likes_by_user[user_id] += 1
            elif row.get("feedback_type") == "dislike":
                dislikes_by_user[user_id] += 1
            created_at = _parse_dt(row.get("created_at"))
            if created_at and created_at > last_feedback.get(user_id, min_dt):
                last_feedback[user_id] = created_at

        rows = []
        for user in users:
            user_id = user.get("id")
            preferences = user.get("preferences") or {}
            hard = preferences.get("hard_filters") or {}
            soft = preferences.get("soft_preferences") or {}
            sent = notifications_by_user[user_id]
            responded = feedback_by_user[user_id]
            rows.append(
                {
                    "id": user_id,
                    "telegram_id": user.get("telegram_id"),
                    "telegram_username": user.get("telegram_username"),
                    "is_active": bool(user.get("is_active")),
                    "onboarding_completed": bool(user.get("onboarding_completed")),
                    "onboarding_step": _safe_int(user.get("onboarding_step")),
                    "created_at": user.get("created_at"),
                    "updated_at": user.get("updated_at"),
                    "notifications_sent": sent,
                    "feedback_total": responded,
                    "likes": likes_by_user[user_id] or _safe_int(user.get("total_likes")),
                    "dislikes": dislikes_by_user[user_id] or _safe_int(user.get("total_dislikes")),
                    "response_rate_pct": _pct(responded, sent),
                    "last_notification_at": last_notification.get(user_id).isoformat()
                    if user_id in last_notification
                    else None,
                    "last_feedback_at": last_feedback.get(user_id).isoformat()
                    if user_id in last_feedback
                    else None,
                    "operation_type": hard.get("operation_type"),
                    "neighborhoods": hard.get("neighborhoods") or [],
                    "max_price_usd": hard.get("max_price_usd"),
                    "min_rooms": hard.get("min_rooms"),
                    "ideal_description": soft.get("ideal_description"),
                }
            )
        return sorted(
            rows,
            key=lambda item: (
                item["onboarding_completed"],
                item["feedback_total"],
                item["notifications_sent"],
            ),
            reverse=True,
        )

    def _match_quality(self, matches: list[dict]) -> dict[str, Any]:
        by_band: Counter[str] = Counter(row.get("band") or "unknown" for row in matches)
        gaps: Counter[str] = Counter()
        for row in matches:
            for gap in row.get("gaps") or []:
                gaps[str(gap)] += 1
        return {
            "by_band": [
                {"band": band, "count": count}
                for band, count in by_band.most_common()
            ],
            "top_gaps": [
                {"gap": gap, "count": count}
                for gap, count in gaps.most_common(8)
            ],
        }

    def _source_quality(self, events: list[dict]) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "source": "",
                "accepted": 0,
                "rejected": 0,
                "errors": 0,
                "_scores": [],
                "_reasons": Counter(),
            }
        )
        for event in events:
            source = event.get("source") or "unknown"
            bucket = grouped[source]
            bucket["source"] = source
            status = event.get("status")
            if status == "accepted":
                bucket["accepted"] += 1
            elif status == "rejected":
                bucket["rejected"] += 1
            elif status == "error":
                bucket["errors"] += 1
            bucket["_scores"].append(_safe_float(event.get("quality_score")))
            reason = event.get("reason")
            if reason:
                bucket["_reasons"][str(reason)] += 1

        rows = []
        for bucket in grouped.values():
            total = bucket["accepted"] + bucket["rejected"] + bucket["errors"]
            rows.append(
                {
                    "source": bucket["source"],
                    "accepted": bucket["accepted"],
                    "rejected": bucket["rejected"],
                    "errors": bucket["errors"],
                    "total": total,
                    "acceptance_rate_pct": _pct(bucket["accepted"], total),
                    "avg_quality_score": _avg(bucket["_scores"]),
                    "top_reasons": [
                        {"reason": reason, "count": count}
                        for reason, count in bucket["_reasons"].most_common(5)
                    ],
                }
            )
        return sorted(rows, key=lambda item: item["total"], reverse=True)

    def _recent_feedback(self, feedback: list[dict]) -> list[dict[str, Any]]:
        rows = []
        for row in feedback:
            listing = row.get("analyzed_listings") or {}
            raw = listing.get("raw_listings") or {}
            rows.append(
                {
                    "created_at": row.get("created_at"),
                    "feedback_type": row.get("feedback_type"),
                    "reason": row.get("reason"),
                    "reason_label": _reason_label(row.get("reason")),
                    "user_id": row.get("user_id"),
                    "listing_id": row.get("analyzed_listing_id"),
                    "title": raw.get("title"),
                    "url": raw.get("url"),
                    "operation_type": raw.get("operation_type"),
                    "neighborhood": listing.get("neighborhood"),
                    "rooms": listing.get("rooms"),
                    "price_usd": listing.get("price_usd"),
                    "summary": listing.get("executive_summary"),
                }
            )
        return rows

    def _learning_questions(
        self,
        *,
        users: list[dict],
        recent_notifications: list[dict],
        recent_feedback: list[dict],
        ingestion_events: list[dict],
    ) -> list[dict[str, str]]:
        questions = []
        onboarded = [user for user in users if user.get("onboarding_completed")]
        if onboarded and not recent_notifications:
            questions.append(
                {
                    "title": "Hay usuarios onboarded sin envios recientes",
                    "why": "El problema puede estar en scraping, filtros restrictivos o threshold de matching.",
                }
            )
        if recent_notifications and _pct(len(recent_feedback), len(recent_notifications)) < 25:
            questions.append(
                {
                    "title": "La tasa de respuesta esta baja",
                    "why": "Tal vez el mensaje no pide feedback con claridad o los matches no generan reaccion.",
                }
            )
        dislikes = [row for row in recent_feedback if row.get("feedback_type") == "dislike"]
        if dislikes and _pct(len(dislikes), len(recent_feedback)) > 60:
            questions.append(
                {
                    "title": "Predominan los dislikes",
                    "why": "Mira motivos: precio, zona y features faltantes suelen indicar filtros incompletos.",
                }
            )
        errors = [event for event in ingestion_events if event.get("status") == "error"]
        if errors:
            questions.append(
                {
                    "title": "Hay errores de ingestion en la ventana",
                    "why": "Los errores reducen el universo de matches y pueden sesgar el aprendizaje.",
                }
            )
        if not questions:
            questions.append(
                {
                    "title": "Hay senales suficientes para revisar manualmente",
                    "why": "Mira razones de feedback y usuarios silenciosos antes de tocar el scoring.",
                }
            )
        return questions
