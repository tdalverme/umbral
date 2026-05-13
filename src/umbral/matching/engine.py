"""Matching service explicable."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

import structlog

from umbral.analysis import PersonalizedMatchAnalyzer
from umbral.config import get_settings
from umbral.database import (
    AnalyzedListingRepository,
    FeedbackRepository,
    NotificationRepository,
    UserListingMatchRepository,
    UserRepository,
)
from umbral.models import UserListingMatch, UserPreferences
from umbral.models.user import HardFilters, SoftPreferences
from umbral.scoring import SCORING_VERSION, ScoringEngine, ScoringResult

logger = structlog.get_logger()


@dataclass
class MatchResult:
    """Resultado listo para feed/notificacion."""

    listing_id: str
    listing_data: dict
    scoring: ScoringResult
    personalized_analysis: Optional[dict] = None

    @property
    def similarity_score(self) -> float:
        return self.scoring.normalized_score

    @property
    def final_score(self) -> float:
        return self.scoring.normalized_score


def _parse_vector(value) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, list):
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _preferences_from_user(user: dict) -> UserPreferences:
    prefs_dict = user.get("preferences", {}) or {}
    hard_dict = prefs_dict.get("hard_filters", {}) or {}
    soft_dict = prefs_dict.get("soft_preferences", {}) or {}
    return UserPreferences(
        hard_filters=HardFilters(**hard_dict),
        soft_preferences=SoftPreferences(**soft_dict),
    )


class MatchingService:
    """Orquestador de candidatos, scoring, cache y notificaciones."""

    def __init__(
        self,
        user_repo: UserRepository | None = None,
        listing_repo: AnalyzedListingRepository | None = None,
        notification_repo: NotificationRepository | None = None,
        match_repo: UserListingMatchRepository | None = None,
        feedback_repo: FeedbackRepository | None = None,
        scoring_engine: ScoringEngine | None = None,
        personalized_match_analyzer: PersonalizedMatchAnalyzer | None = None,
    ):
        self.user_repo = user_repo or UserRepository()
        self.listing_repo = listing_repo or AnalyzedListingRepository()
        self.notification_repo = notification_repo or NotificationRepository()
        self.match_repo = match_repo or UserListingMatchRepository()
        self.feedback_repo = feedback_repo or FeedbackRepository()
        self.scoring_engine = scoring_engine or ScoringEngine()
        self.personalized_match_analyzer = personalized_match_analyzer

    def get_feed(self, user_id: str, *, limit: int = 50) -> list[dict]:
        """Devuelve matches cacheados para un futuro frontend."""
        return self.match_repo.get_fresh_for_user(user_id, limit=limit)

    async def find_matches_for_user(
        self,
        user_id: str,
        preferences: UserPreferences,
        preference_vector: Optional[list[float]] = None,
        limit: int = 20,
        candidate_limit: int = 300,
        min_score: int = 75,
    ) -> list[MatchResult]:
        candidates = self.listing_repo.find_candidates_for_user(
            preferences,
            limit=candidate_limit,
        )
        if not candidates:
            logger.info("No hay candidatos para usuario", user_id=user_id)
            return []

        feedback_examples = self.feedback_repo.get_user_feedback(user_id)
        matches: list[MatchResult] = []
        cache_rows: list[UserListingMatch] = []

        for candidate in candidates:
            analyzed_id = candidate["id"]
            if self.notification_repo.was_sent(user_id, analyzed_id):
                continue

            scoring = self.scoring_engine.score(
                candidate,
                preferences,
                preference_vector=preference_vector,
                feedback_examples=feedback_examples,
            )
            logger.info(
                "Scoring calculado para candidato",
                analyzed_listing_id=analyzed_id,
                final_score=scoring.final_score,
                eligible=scoring.eligible,
                gaps=scoring.gaps,
            )
            if not scoring.eligible:
                continue

            cache_rows.append(
                UserListingMatch(
                    user_id=user_id,
                    analyzed_listing_id=analyzed_id,
                    final_score=scoring.final_score,
                    band=scoring.band,
                    summary=scoring.summary,
                    criteria_breakdown=[criterion.model_dump() for criterion in scoring.criteria],
                    gaps=scoring.gaps,
                    scoring_version=SCORING_VERSION,
                    preference_version="1",
                )
            )

            if scoring.final_score >= min_score:
                matches.append(
                    MatchResult(
                        listing_id=analyzed_id,
                        listing_data=self._notification_listing_data(candidate),
                        scoring=scoring,
                        personalized_analysis=scoring.to_personalized_analysis(),
                    )
                )

        if cache_rows:
            self.match_repo.upsert_many(cache_rows)

        matches.sort(key=lambda match: match.scoring.final_score, reverse=True)
        matches = matches[:limit]
        for match in matches:
            match.personalized_analysis = await self._personalized_analysis(
                preferences=preferences,
                listing_data=match.listing_data,
                scoring=match.scoring,
            )
        logger.info(
            "Matches explicables encontrados",
            user_id=user_id,
            candidates=len(candidates),
            cached=len(cache_rows),
            above_threshold=len(matches),
        )
        return matches

    async def process_new_listings(
        self,
        listing_ids: Optional[list[str]] = None,
    ) -> dict:
        """Procesa usuarios activos y envia notificaciones de top matches."""
        from umbral.bot import UmbralBot

        stats = {
            "users_processed": 0,
            "matches_found": 0,
            "notifications_sent": 0,
            "errors": 0,
        }
        active_users = self.user_repo.get_active_users()
        if not active_users:
            logger.info("No hay usuarios activos para notificar")
            return stats

        bot = UmbralBot()
        for user in active_users:
            try:
                preferences = _preferences_from_user(user)
                preference_vector = _parse_vector(user.get("preference_vector"))
                matches = await self.find_matches_for_user(
                    user_id=user["id"],
                    preferences=preferences,
                    preference_vector=preference_vector,
                    limit=3,
                )
                stats["users_processed"] += 1
                stats["matches_found"] += len(matches)

                for match in matches:
                    success = await bot.send_listing_notification(
                        telegram_id=user["telegram_id"],
                        listing_data=match.listing_data,
                        similarity_score=match.final_score,
                        personalized_analysis=match.personalized_analysis,
                    )
                    if success:
                        self.notification_repo.create(
                            user_id=user["id"],
                            analyzed_listing_id=match.listing_id,
                            final_score=match.scoring.final_score,
                        )
                        self.match_repo.mark_notified(user["id"], match.listing_id)
                        stats["notifications_sent"] += 1
            except Exception as e:
                import traceback

                logger.error(
                    "Error procesando usuario",
                    user_id=user.get("id"),
                    error=str(e),
                    traceback=traceback.format_exc(),
                )
                stats["errors"] += 1

        logger.info("Ciclo de matching completado", **stats)
        return stats

    async def run_matching_cycle(self):
        logger.info("Iniciando ciclo de matching explicable")
        return await self.process_new_listings()

    async def _personalized_analysis(
        self,
        *,
        preferences: UserPreferences,
        listing_data: dict,
        scoring: ScoringResult,
    ) -> object:
        fallback = scoring.to_personalized_analysis()
        threshold = get_settings().personalized_analysis_threshold
        if scoring.normalized_score < threshold:
            return fallback

        try:
            analyzer = self.personalized_match_analyzer
            if analyzer is None:
                analyzer = PersonalizedMatchAnalyzer()
                self.personalized_match_analyzer = analyzer
            analysis_listing_data = self._notification_listing_data(listing_data)
            analysis_listing_data["criteria"] = [criterion.model_dump() for criterion in scoring.criteria]
            analysis_listing_data["gaps"] = scoring.gaps
            return await analyzer.generate(
                preferences=preferences,
                listing_data=analysis_listing_data,
                similarity_score=scoring.normalized_score,
            )
        except Exception as e:
            logger.warning(
                "No se pudo generar analisis personalizado; usando resumen explicable",
                error=str(e),
            )
            return fallback

    def _notification_listing_data(self, candidate: dict) -> dict:
        """Aplana analyzed + raw para el adapter de Telegram."""
        raw = candidate.get("raw_listings") or {}
        return {
            **raw,
            **candidate,
            "id": candidate["id"],
            "analyzed_listing_id": candidate["id"],
            "raw_listing_id": candidate.get("raw_listing_id"),
            "price": raw.get("price") or candidate.get("price_original"),
            "currency": raw.get("currency") or candidate.get("currency_original"),
            "features": raw.get("features") or candidate.get("features") or {},
            "images": raw.get("images") or [],
            "url": raw.get("url") or candidate.get("url"),
            "title": raw.get("title") or candidate.get("title"),
            "location": raw.get("location") or candidate.get("neighborhood"),
            "maintenance_fee": raw.get("maintenance_fee"),
            "size_total": raw.get("size_total"),
            "size_covered": raw.get("size_covered"),
            "parking_spaces": raw.get("parking_spaces"),
        }


MatchingEngine = MatchingService
