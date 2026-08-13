"""Contract conformance of the learning proposals endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.support.feedback import FeedbackTestContext
from umbral.api.dependencies import RuntimeDependencies
from umbral.api.routers.learning import router as learning_router
from umbral.application.feedback.contracts import LearningProposal
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


def _app(context: FeedbackTestContext, principal: CurrentPrincipal) -> TestClient:
    profile = context.add_profile(owner_id=principal.user_id)
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
        feedback=context.service,
    )
    app = FastAPI()
    from umbral.api.routers.learning import configure_learning_routes

    configure_learning_routes(deps)
    app.include_router(learning_router)
    app._umbral_learning_profile = profile  # type: ignore[attr-defined]
    return TestClient(app)


def _seed_pending_proposal(
    context: FeedbackTestContext, profile: SearchProfile
) -> LearningProposal:
    concept = next(iter(context.concepts.rows))
    concept_id = context.concepts.rows[concept]
    context.service.register_policy_version(
        policy_key="learning-v1",
        payload={
            "contract_version": "1",
            "learning_policy_version": "learning-v1",
            "min_signals": 2,
            "window_days": 90,
            "min_signal_confidence": 1.0,
            "cooldown_days": 7,
            "proposal_expiration_days": 30,
            "default_suggested_weight": 0.3,
            "default_suggested_confidence": 0.6,
        },
        correlation_id=uuid4(),
    )
    version = context.service.policies.latest_version("learning-v1")
    assert version is not None
    from datetime import timedelta

    from umbral.application.feedback.contracts import LearningProposal, ProposalChange

    proposal = LearningProposal(
        proposal_id=uuid4(),
        profile_id=profile.profile_id,
        concept_id=concept_id,
        concept_key=concept,
        policy_version_id=version.version_id,
        policy_version="1",
        change=ProposalChange(
            kind="preference_fact",
            concept_key=concept,
            polarity="negative",
            suggested_weight=0.3,
            suggested_confidence=0.6,
            value=None,
        ),
        prior_fact=None,
        evidence_refs=({"feedback_event_id": "a" * 32},),
        state="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        superseded_by=None,
        applied_profile_version_id=None,
        applied_run_id=None,
        created_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
    )
    context.service.proposals.insert(proposal)
    return proposal


def test_list_proposals_returns_pending_items() -> None:
    principal = _principal()
    context = FeedbackTestContext()
    app = _app(context, principal)
    profile = getattr(app.app, "_umbral_learning_profile")
    _seed_pending_proposal(context, profile)
    response = app.get(
        f"/api/v1/search-profiles/{profile.profile_id}/learning-proposals",
        params={"state": "pending"},
        cookies={COOKIE: "token"},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["state"] == "pending"
    assert items[0]["change"]["polarity"] == "negative"


def test_expand_proposal_edits_the_change() -> None:
    principal = _principal()
    context = FeedbackTestContext()
    app = _app(context, principal)
    profile = getattr(app.app, "_umbral_learning_profile")
    proposal = _seed_pending_proposal(context, profile)
    response = app.put(
        f"/api/v1/search-profiles/{profile.profile_id}/learning-proposals/{proposal.proposal_id}",
        json={
            "change": {
                "concept_key": proposal.change.concept_key,
                "polarity": "positive",
                "suggested_weight": 0.5,
                "suggested_confidence": 0.7,
                "value": None,
            }
        },
        cookies={COOKIE: "token"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["change"]["polarity"] == "positive"
    assert response.json()["change"]["suggested_weight"] == 0.5


def test_reject_proposal_transitions_state() -> None:
    principal = _principal()
    context = FeedbackTestContext()
    app = _app(context, principal)
    profile = getattr(app.app, "_umbral_learning_profile")
    proposal = _seed_pending_proposal(context, profile)
    response = app.post(
        f"/api/v1/search-profiles/{profile.profile_id}/learning-proposals/{proposal.proposal_id}/reject",
        cookies={COOKIE: "token"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "rejected"


def test_confirm_on_unavailable_service_returns_409() -> None:
    principal = _principal()
    context = FeedbackTestContext()
    app = _app(context, principal)
    profile = getattr(app.app, "_umbral_learning_profile")
    proposal = _seed_pending_proposal(context, profile)
    response = app.post(
        f"/api/v1/search-profiles/{profile.profile_id}/learning-proposals/{proposal.proposal_id}/confirm",
        cookies={COOKIE: "token"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "feedback.state_error"


def test_learning_endpoints_require_a_session() -> None:
    principal = _principal()
    context = FeedbackTestContext()
    app = _app(context, principal)
    response = app.get(
        "/api/v1/search-profiles/00000000-0000-0000-0000-000000000000/learning-proposals"
    )
    assert response.status_code == 401
