"""FastAPI app minima para el futuro frontend de Umbral."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from umbral.api.admin import router as admin_router
from umbral.database import FeedbackRepository, UserListingMatchRepository, UserRepository
from umbral.matching import MatchingService
from umbral.matching.engine import _parse_vector, _preferences_from_user
from umbral.models.user import UserFeedback


class FeedbackRequest(BaseModel):
    feedback_type: str


def create_app() -> FastAPI:
    app = FastAPI(title="Umbral API", version="0.1.0")
    app.include_router(admin_router)
    users = UserRepository()
    matches = UserListingMatchRepository()
    feedback = FeedbackRepository()
    matching = MatchingService(user_repo=users, match_repo=matches, feedback_repo=feedback)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/users/{user_id}/feed")
    def get_feed(user_id: str, limit: int = 50) -> dict:
        return {"items": matching.get_feed(user_id, limit=limit)}

    @app.post("/users/{user_id}/matches/refresh")
    async def refresh_matches(user_id: str, limit: int = 50) -> dict:
        user = users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="user not found")
        result = await matching.find_matches_for_user(
            user_id=user_id,
            preferences=_preferences_from_user(user),
            preference_vector=_parse_vector(user.get("preference_vector")),
            limit=limit,
        )
        return {
            "items": [
                {
                    "analyzed_listing_id": item.listing_id,
                    "final_score": item.scoring.final_score,
                    "band": item.scoring.band,
                    "summary": item.scoring.summary,
                    "criteria": [criterion.model_dump() for criterion in item.scoring.criteria],
                    "gaps": item.scoring.gaps,
                }
                for item in result
            ]
        }

    @app.post("/users/{user_id}/matches/{analyzed_listing_id}/feedback")
    def create_feedback(user_id: str, analyzed_listing_id: str, request: FeedbackRequest) -> dict:
        if request.feedback_type not in {"like", "dislike"}:
            raise HTTPException(status_code=400, detail="feedback_type must be like or dislike")
        row = feedback.create(
            UserFeedback(
                user_id=user_id,
                analyzed_listing_id=analyzed_listing_id,
                feedback_type=request.feedback_type,
            )
        )
        matches.mark_feedback(user_id, analyzed_listing_id, request.feedback_type)
        return {"feedback": row}

    return app


app = create_app()
