"""Contract conformance of the feedback and decision-items endpoints."""
# ruff: noqa: E501

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.support.feedback import FeedbackTestContext
from umbral.api.dependencies import RuntimeDependencies
from umbral.api.routers.feedback import router as feedback_router
from umbral.application.identity.authorization import AccessControl
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.application.radar.contracts import SearchProfile
from umbral.infrastructure.config.settings import Settings

COOKIE = "umbral_test_session"


class FakeAccessControl:
    def __init__(self, principal: CurrentPrincipal | None) -> None:
        self.principal = principal

    def authorize(
        self,
        token: str,
        action: str,
        resource_owner_id: UUID | None,
        now: datetime,
        correlation_id: UUID | None,
    ) -> CurrentPrincipal:
        del token, action, resource_owner_id, now, correlation_id
        if self.principal is None:
            raise IdentityError("auth.session_required", status=401, recovery="sign_in")
        return self.principal


def _settings() -> Settings:
    return Settings.from_environment(
        {
            "UMBRAL_ENV": "local",
            "UMBRAL_RELEASE_ID": "foundation-local",
            "UMBRAL_RELEASE_MANIFEST": "<local>",
            "DATABASE_URL": "postgresql://umbral:local@127.0.0.1/umbral",
            "REDIS_URL": "redis://127.0.0.1:6379/0",
            "OBJECT_STORE_BACKEND": "filesystem",
            "OBJECT_STORE_ROOT": ".umbral-local",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
            "UMBRAL_API_BASE_URL": "http://127.0.0.1:8000",
            "SESSION_COOKIE_NAME": COOKIE,
            "SESSION_SECURE": "false",
        }
    )


def _principal() -> CurrentPrincipal:
    return CurrentPrincipal(
        user_id=uuid4(),
        roles=("user",),
        last_activity_at=datetime.now(timezone.utc),
    )


def _app(
    principal: CurrentPrincipal | None,
    context: FeedbackTestContext | None = None,
) -> TestClient:
    ctx = context or FeedbackTestContext()
    profile = ctx.add_profile(owner_id=principal.user_id) if principal else None
    deps = RuntimeDependencies(
        settings=_settings(),
        release=None,  # type: ignore[arg-type]
        readiness=None,  # type: ignore[arg-type]
        object_store=None,  # type: ignore[arg-type]
        identity_store=None,  # type: ignore[arg-type]
        identity_access=None,  # type: ignore[arg-type]
        access_control=cast(AccessControl, FakeAccessControl(principal)),
        administration=None,  # type: ignore[arg-type]
        ingestion=None,  # type: ignore[arg-type]
        radar=None,
        scoring=None,
        feedback=ctx.service,
    )
    app = FastAPI()
    from umbral.api.routers.feedback import configure_feedback_routes

    configure_feedback_routes(deps)
    app.include_router(feedback_router)
    app._umbral_feedback_profile = profile  # type: ignore[attr-defined]
    return TestClient(app)


def _profile_of(app: TestClient) -> SearchProfile:
    return cast(SearchProfile, getattr(app.app, "_umbral_feedback_profile"))


def test_post_feedback_records_and_returns_decision_state() -> None:
    principal = _principal()
    app = _app(principal)
    profile = _profile_of(app)
    response = app.post(
        f"/api/v1/search-profiles/{profile.profile_id}/feedback",
        json={
            "listing_id": str(uuid4()),
            "event_type": "like",
            "reason_keys": ["price_fits"],
            "idempotency_key": "k-1",
        },
        cookies={COOKIE: "token"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["event_type"] == "like"
    assert body["decision_state"] == "like"
    assert body["reason_keys"] == ["price_fits"]
    assert body["superseded"] is False
    assert body["noop"] is False


def test_post_feedback_replay_is_a_noop() -> None:
    principal = _principal()
    app = _app(principal)
    profile = _profile_of(app)
    payload = {
        "listing_id": str(uuid4()),
        "event_type": "save",
        "idempotency_key": "k-1",
    }
    first = app.post(
        f"/api/v1/search-profiles/{profile.profile_id}/feedback",
        json=payload,
        cookies={COOKIE: "token"},
    )
    second = app.post(
        f"/api/v1/search-profiles/{profile.profile_id}/feedback",
        json=payload,
        cookies={COOKIE: "token"},
    )
    assert first.json()["event_id"] == second.json()["event_id"]
    assert second.json()["noop"] is True


def test_post_feedback_terminal_contacted_returns_409() -> None:
    principal = _principal()
    app = _app(principal)
    profile = _profile_of(app)
    listing_id = str(uuid4())
    app.post(
        f"/api/v1/search-profiles/{profile.profile_id}/feedback",
        json={"listing_id": listing_id, "event_type": "contacted", "idempotency_key": "k-1"},
        cookies={COOKIE: "token"},
    )
    response = app.post(
        f"/api/v1/search-profiles/{profile.profile_id}/feedback",
        json={"listing_id": listing_id, "event_type": "like", "idempotency_key": "k-2"},
        cookies={COOKIE: "token"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "feedback_terminal"


def test_post_feedback_unknown_reason_returns_400() -> None:
    principal = _principal()
    app = _app(principal)
    profile = _profile_of(app)
    response = app.post(
        f"/api/v1/search-profiles/{profile.profile_id}/feedback",
        json={
            "listing_id": str(uuid4()),
            "event_type": "dislike",
            "reason_keys": ["ghost"],
            "idempotency_key": "k-1",
        },
        cookies={COOKIE: "token"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "feedback.validation_failed"


def test_post_feedback_requires_a_session() -> None:
    app = _app(None)
    response = app.post(
        "/api/v1/search-profiles/00000000-0000-0000-0000-000000000000/feedback",
        json={
            "listing_id": "00000000-0000-0000-0000-000000000001",
            "event_type": "like",
            "idempotency_key": "k-1",
        },
    )
    assert response.status_code == 401


def test_decision_items_filters_by_state() -> None:
    principal = _principal()
    app = _app(principal)
    profile = _profile_of(app)
    app.post(
        f"/api/v1/search-profiles/{profile.profile_id}/feedback",
        json={"listing_id": str(uuid4()), "event_type": "save", "idempotency_key": "k-1"},
        cookies={COOKIE: "token"},
    )
    response = app.get(
        f"/api/v1/search-profiles/{profile.profile_id}/decision-items",
        params={"decision_state": "save"},
        cookies={COOKIE: "token"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"][0]["decision_state"] == "save"
