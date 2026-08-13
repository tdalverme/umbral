"""Contract conformance of the explanation and comparison endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.fakes.radar import (
    FakeCandidateListingReader,
    FakeEventRepository,
    FakeItemRepository,
    FakeListingReader,
    FakeProfileVersionRepository,
    FakeRunRepository,
    FakeSearchProfileRepository,
)
from tests.support.radar import build_listing, build_profile
from tests.support.scoring import (
    ScoringTestContext,
    build_item,
    build_run,
)
from umbral.api.dependencies import RuntimeDependencies
from umbral.api.routers.comparisons import router as comparisons_router
from umbral.api.routers.explanations import router as explanations_router
from umbral.application.identity.authorization import AccessControl
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.application.radar.contracts import (
    RecommendationItem,
    RecommendationRun,
    SearchProfile,
)
from umbral.application.radar.service import RadarService
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.radar.contract_loader import (
    load_events_registry,
    load_scoring_baseline,
    load_search_profile_policy,
)

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


def _scoring_context(
    comparator_enabled: bool = False,
) -> tuple[ScoringTestContext, UUID, UUID, UUID, UUID]:
    context = ScoringTestContext(comparator_enabled=comparator_enabled)
    owner_id = uuid4()
    profile_id = uuid4()
    listing_id = uuid4()
    run_id = uuid4()
    run = build_run(profile_id=profile_id, profile_version_id=uuid4(), run_id=run_id)
    context.runs.rows[run_id] = run
    context.items.items_by_run[run_id] = [
        build_item(run_id, listing_id, position=0),
        build_item(run_id, uuid4(), position=1),
    ]
    context.listings.rows[listing_id] = build_listing(listing_id=listing_id)
    profile = build_profile(owner_id=owner_id, profile_id=profile_id)
    context.profiles.rows[profile_id] = profile
    from umbral.application.scoring.contracts import CriterionEvaluation

    context.evaluations.rows.append(
        CriterionEvaluation(
            evaluation_id=uuid4(),
            run_id=run_id,
            listing_id=listing_id,
            criterion_key="presupuesto",
            criterion_version="policy:scoring-policy-v1",
            matcher_type="numeric_range",
            params={},
            input_refs=(),
            score=0.3,
            confidence=1.0,
            state="match",
            contribution=0.075,
            reason_code="budget_within_headroom",
            evidence_refs=(
                {"kind": "listing_field", "ref": "total_cost", "version": "silver-v1"},
            ),
            created_at=datetime.now(timezone.utc),
            correlation_id=uuid4(),
        )
    )
    return context, owner_id, profile_id, run_id, listing_id


def _radar(
    profile: SearchProfile,
    run: RecommendationRun | None = None,
    items: tuple[RecommendationItem, ...] = (),
) -> RadarService:
    shared_items: dict[UUID, list[RecommendationItem]] = {}
    runs = FakeRunRepository(items_by_run=shared_items)
    items_repo = FakeItemRepository(items_by_run=shared_items)
    runs.items_by_run = shared_items
    service = RadarService(
        profiles=FakeSearchProfileRepository(),
        versions=FakeProfileVersionRepository(),
        runs=runs,
        items=items_repo,
        events=FakeEventRepository(),
        candidates=FakeCandidateListingReader(),
        listings=FakeListingReader(),
        policy=load_search_profile_policy(),
        scoring=load_scoring_baseline(),
        events_registry=load_events_registry(),
        job_runtime=None,
    )
    service.profiles.insert(profile)
    if run is not None:
        service.runs.insert(run)
        items_repo.items_by_run[run.run_id] = list(items)
    return service


def _app(
    principal: CurrentPrincipal | None,
    scoring_context: ScoringTestContext | None = None,
    radar: RadarService | None = None,
) -> TestClient:
    context = scoring_context or ScoringTestContext()
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
        radar=radar,
        scoring=context.service,
    )
    app = FastAPI()
    from umbral.api.routers.comparisons import configure_comparisons_routes
    from umbral.api.routers.explanations import configure_explanations_routes

    configure_explanations_routes(deps)
    configure_comparisons_routes(deps)
    app.include_router(explanations_router)
    app.include_router(comparisons_router)
    return TestClient(app)


PRINCIPAL = CurrentPrincipal(
    uuid4(), ("user",), datetime(2026, 8, 1, tzinfo=timezone.utc)
)


def _principal_for(owner_id: UUID) -> CurrentPrincipal:
    return CurrentPrincipal(
        owner_id, ("user",), datetime(2026, 8, 1, tzinfo=timezone.utc)
    )


def test_explanation_by_listing_returns_breakdown() -> None:
    context, owner_id, profile_id, run_id, listing_id = _scoring_context()
    radar = _radar(
        profile=context.profiles.rows[profile_id],
        run=context.runs.rows[run_id],
        items=tuple(context.items.items_by_run.get(run_id, ())),
    )
    client = _app(_principal_for(owner_id), context, radar)
    response = client.get(
        f"/api/v1/search-profiles/{profile_id}/explanations/{listing_id}",
        cookies={COOKIE: "token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["score_version"] == "scoring-policy-v1"
    assert body["listing_id"] == str(listing_id)
    assert body["reasons"][0]["criterion_key"] == "presupuesto"
    assert body["reasons"][0]["evidence_refs"][0]["kind"] == "listing_field"
    assert "budget_max" in body["satisfied_filters"]


def test_explanation_list_paginates() -> None:
    context, owner_id, profile_id, run_id, _ = _scoring_context()
    radar = _radar(
        profile=context.profiles.rows[profile_id],
        run=context.runs.rows[run_id],
        items=tuple(context.items.items_by_run.get(run_id, ())),
    )
    client = _app(_principal_for(owner_id), context, radar)
    response = client.get(
        f"/api/v1/search-profiles/{profile_id}/explanations",
        cookies={COOKIE: "token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == str(run_id)
    assert len(body["items"]) == 2
    assert body["next_after_position"] is None


def test_explanation_listing_outside_run_is_typed_404() -> None:
    context, owner_id, profile_id, run_id, _ = _scoring_context()
    radar = _radar(
        profile=context.profiles.rows[profile_id],
        run=context.runs.rows[run_id],
        items=tuple(context.items.items_by_run.get(run_id, ())),
    )
    client = _app(_principal_for(owner_id), context, radar)
    response = client.get(
        f"/api/v1/search-profiles/{profile_id}/explanations/{uuid4()}",
        cookies={COOKIE: "token"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "scoring.not_found"


def test_anonymous_explanation_is_rejected() -> None:
    client = _app(None)
    response = client.get(f"/api/v1/search-profiles/{uuid4()}/explanations/{uuid4()}")
    assert response.status_code == 401


def test_comparison_endpoint_builds_the_matrix() -> None:
    context, owner_id, profile_id, run_id, listing_id = _scoring_context()
    radar = _radar(
        profile=context.profiles.rows[profile_id],
        run=context.runs.rows[run_id],
        items=tuple(context.items.items_by_run.get(run_id, ())),
    )
    client = _app(_principal_for(owner_id), context, radar)
    second = uuid4()
    context.items.items_by_run[run_id].append(build_item(run_id, second, position=2))
    response = client.post(
        f"/api/v1/search-profiles/{profile_id}/comparisons",
        cookies={COOKIE: "token"},
        json={"listing_ids": [str(listing_id), str(second)]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 6
    assert any(
        d["kind"] == "fixed" and d["key"] == "total_cost" for d in body["dimensions"]
    )
    assert any(
        d["kind"] == "criterion" and d["key"] == "balcon" for d in body["dimensions"]
    )
    assert len(body["cells"]) == len(body["listings"]) * len(body["dimensions"])


def test_comparison_over_limit_is_rejected_with_typed_problem() -> None:
    context, owner_id, profile_id, run_id, listing_id = _scoring_context()
    radar = _radar(
        profile=context.profiles.rows[profile_id],
        run=context.runs.rows[run_id],
        items=tuple(context.items.items_by_run.get(run_id, ())),
    )
    client = _app(_principal_for(owner_id), context, radar)
    response = client.post(
        f"/api/v1/search-profiles/{profile_id}/comparisons",
        cookies={COOKIE: "token"},
        json={"listing_ids": [str(uuid4()) for _ in range(7)]},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "scoring.validation_failed"


def test_shortlist_endpoints_are_idempotent() -> None:
    context, owner_id, profile_id, run_id, listing_id = _scoring_context(
        comparator_enabled=True
    )
    radar = _radar(
        profile=context.profiles.rows[profile_id],
        run=context.runs.rows[run_id],
        items=tuple(context.items.items_by_run.get(run_id, ())),
    )
    client = _app(_principal_for(owner_id), context, radar)
    response = client.put(
        f"/api/v1/search-profiles/{profile_id}/comparison-shortlist",
        cookies={COOKIE: "token"},
        json={"listing_ids": [str(listing_id)]},
    )
    assert response.status_code == 200
    stored = client.get(
        f"/api/v1/search-profiles/{profile_id}/comparison-shortlist",
        cookies={COOKIE: "token"},
    )
    assert stored.status_code == 200
    assert stored.json()["listing_ids"] == [str(listing_id)]
