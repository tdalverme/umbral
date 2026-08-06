"""Product surface for search profiles (the radar)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.application.radar.contracts import (
    RadarNotAccessible,
    RadarStateError,
    RadarValidationError,
    RecommendationRun,
    SearchProfile,
)
from umbral.application.radar.service import RadarService
from umbral.domain.errors import ConcurrencyConflict

router = APIRouter(prefix="/api/v1", tags=["Search Profiles"])
_dependencies: RuntimeDependencies | None = None

ProfileState = Literal["active", "paused", "archived"]
RunState = Literal["pending", "running", "succeeded", "failed"]


class CreateSearchProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    zones: list[str] = Field(min_length=1, max_length=15)
    budget_max: float = Field(gt=0)
    budget_min: float | None = None
    min_rooms: int = Field(default=0, ge=0, le=200)
    surface_min: float | None = None
    surface_max: float | None = None
    unknown_strategy: dict[str, str] | None = None


class UpdateSearchProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=80)
    zones: list[str] | None = None
    budget_max: float | None = Field(default=None, gt=0)
    budget_min: float | None = None
    min_rooms: int | None = Field(default=None, ge=0, le=200)
    surface_min: float | None = None
    surface_max: float | None = None


class StatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ProfileState


class RunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: UUID
    state: RunState
    trigger: str
    score_policy_version: str
    candidate_count: int
    published_item_count: int
    failure_code: str | None = None
    created_at: datetime
    finished_at: datetime | None = None

    @classmethod
    def from_domain(cls, run: RecommendationRun) -> "RunResponse":
        return cls(
            run_id=run.run_id,
            state=run.state,
            trigger=run.trigger,
            score_policy_version=run.score_policy_version,
            candidate_count=run.candidate_count,
            published_item_count=run.published_item_count,
            failure_code=run.failure_code,
            created_at=run.created_at,
            finished_at=run.finished_at,
        )


class SearchProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search_profile_id: UUID
    name: str
    operation: str
    zones: list[str]
    budget_max: float
    budget_min: float | None = None
    min_rooms: int
    surface_min: float | None = None
    surface_max: float | None = None
    status: ProfileState
    unknown_strategy: dict[str, str]
    version: int
    created_at: datetime
    updated_at: datetime
    latest_run: RunResponse | None = None

    @classmethod
    def from_domain(
        cls, profile: SearchProfile, run: RecommendationRun | None = None
    ) -> "SearchProfileResponse":
        return cls(
            search_profile_id=profile.profile_id,
            name=profile.name,
            operation=profile.operation,
            zones=list(profile.zones),
            budget_max=profile.budget_max,
            budget_min=profile.budget_min,
            min_rooms=profile.min_rooms,
            surface_min=profile.surface_min,
            surface_max=profile.surface_max,
            status=profile.status,
            unknown_strategy=dict(profile.unknown_strategy),
            version=profile.version,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            latest_run=RunResponse.from_domain(run) if run is not None else None,
        )


def configure_search_profiles_routes(dependencies: RuntimeDependencies) -> None:
    global _dependencies
    _dependencies = dependencies


def _radar() -> RadarService:
    service = _deps().radar
    if service is None:
        raise RuntimeError("radar service was not configured")
    return service


def _deps() -> RuntimeDependencies:
    if _dependencies is None:
        raise RuntimeError("search profiles routes were not configured")
    return _dependencies


def _correlation(request: Request) -> UUID | None:
    value = request.headers.get("X-Correlation-ID")
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _principal(request: Request) -> CurrentPrincipal:
    cached = cast(
        CurrentPrincipal | None, getattr(request.state, "radar_principal", None)
    )
    if cached is not None:
        return cached
    token = request.cookies.get(_deps().settings.session_cookie_name)
    if not token:
        raise IdentityError("auth.session_required", status=401, recovery="sign_in")
    principal = _deps().access_control.authorize(
        token,
        action="auth.session.read",
        resource_owner_id=None,
        now=datetime.now(timezone.utc),
        correlation_id=_correlation(request),
    )
    request.state.radar_principal = principal
    return principal


def _require(request: Request, action: str) -> CurrentPrincipal:
    principal = _principal(request)
    token = request.cookies.get(_deps().settings.session_cookie_name) or ""
    return _deps().access_control.authorize(
        token,
        action=action,
        resource_owner_id=principal.user_id,
        now=datetime.now(timezone.utc),
        correlation_id=_correlation(request),
    )


def _problem(request: Request, status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": f"https://umbral.invalid/problems/{code}",
            "title": "Radar",
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID", str(uuid4())),
            "correlation_id": request.headers.get("X-Correlation-ID", str(uuid4())),
        },
        headers={"Cache-Control": "no-store"},
    )


def _handle_radar_error(request: Request, error: Exception) -> JSONResponse | None:
    if isinstance(error, RadarValidationError):
        return _problem(
            request, 400, "radar.validation_failed", ",".join(error.error_codes)
        )
    if isinstance(error, RadarNotAccessible):
        return _problem(request, 403, error.code, str(error))
    if isinstance(error, RadarStateError):
        return _problem(request, 400, error.code, str(error))
    if isinstance(error, ConcurrencyConflict):
        return _problem(request, 409, "concurrency.conflict", str(error))
    return None


@router.post(
    "/search-profiles",
    operation_id="createSearchProfile",
    status_code=201,
    response_model=SearchProfileResponse,
    responses={400: {}, 401: {}, 403: {}, 422: {}},
)
async def create_search_profile(
    request: Request,
    body: CreateSearchProfileRequest,
    x_correlation_id: UUID | None = Header(default=None),
) -> SearchProfileResponse | JSONResponse:
    try:
        principal = _principal(request)
        _deps().access_control.authorize(
            request.cookies.get(_deps().settings.session_cookie_name) or "",
            action="product.search_profile.create",
            resource_owner_id=None,
            now=datetime.now(timezone.utc),
            correlation_id=_correlation(request),
        )
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        owner_id = principal.user_id
        profile, run = _radar().create_profile(
            owner_id=owner_id,
            name=body.name,
            zones=tuple(body.zones),
            budget_max=body.budget_max,
            budget_min=body.budget_min,
            min_rooms=body.min_rooms,
            surface_min=body.surface_min,
            surface_max=body.surface_max,
            unknown_strategy=body.unknown_strategy,
            correlation_id=x_correlation_id or uuid4(),
            actor_kind="service",
            actor_id=str(owner_id),
        )
        return SearchProfileResponse.from_domain(profile, run)
    except RadarValidationError as error:
        return _problem(
            request, 400, "radar.validation_failed", ",".join(error.error_codes)
        )
    except Exception as error:
        handled = _handle_radar_error(request, error)
        if handled is not None:
            return handled
        raise


@router.get(
    "/search-profiles",
    operation_id="listSearchProfiles",
    response_model=list[SearchProfileResponse],
    responses={401: {}, 403: {}},
)
async def list_search_profiles(
    request: Request,
    status: ProfileState | None = None,
    x_correlation_id: UUID | None = Header(default=None),
) -> list[SearchProfileResponse] | JSONResponse:
    try:
        principal = _require(request, "product.search_profile.read")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    del x_correlation_id
    owner_id = principal.user_id
    profiles = _radar().list_profiles(owner_id, status)
    return [
        SearchProfileResponse.from_domain(profile, _radar().latest_run_of(profile))
        for profile in profiles
    ]


@router.get(
    "/search-profiles/{search_profile_id}",
    operation_id="getSearchProfile",
    response_model=SearchProfileResponse,
    responses={401: {}, 403: {}, 404: {}},
)
async def get_search_profile(
    request: Request,
    search_profile_id: UUID,
    x_correlation_id: UUID | None = Header(default=None),
) -> SearchProfileResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.search_profile.read")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        profile, run = _radar().profile_with_latest_run(
            principal.user_id, search_profile_id
        )
        return SearchProfileResponse.from_domain(profile, run)
    except RadarNotAccessible as error:
        return _problem(request, 403, error.code, str(error))
    except Exception as error:
        handled = _handle_radar_error(request, error)
        if handled is not None:
            return handled
        raise


@router.patch(
    "/search-profiles/{search_profile_id}",
    operation_id="updateSearchProfile",
    response_model=SearchProfileResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}, 409: {}, 422: {}},
)
async def update_search_profile(
    request: Request,
    search_profile_id: UUID,
    body: UpdateSearchProfileRequest,
    expected_version: int,
    x_correlation_id: UUID | None = Header(default=None),
) -> SearchProfileResponse | JSONResponse:
    try:
        principal = _require(request, "product.search_profile.update")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    changes = body.model_dump(exclude_none=True)
    try:
        profile, run = _radar().update_profile(
            owner_id=principal.user_id,
            profile_id=search_profile_id,
            expected_version=expected_version,
            changes=changes,
            correlation_id=x_correlation_id or uuid4(),
        )
        return SearchProfileResponse.from_domain(profile, run)
    except Exception as error:
        handled = _handle_radar_error(request, error)
        if handled is not None:
            return handled
        raise


@router.post(
    "/search-profiles/{search_profile_id}/status",
    operation_id="setSearchProfileStatus",
    response_model=SearchProfileResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}, 409: {}},
)
async def set_search_profile_status(
    request: Request,
    search_profile_id: UUID,
    body: StatusRequest,
    expected_version: int,
    x_correlation_id: UUID | None = Header(default=None),
) -> SearchProfileResponse | JSONResponse:
    try:
        principal = _require(request, "product.search_profile.status")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        profile, run = _radar().set_status(
            owner_id=principal.user_id,
            profile_id=search_profile_id,
            expected_version=expected_version,
            status=body.status,
            correlation_id=x_correlation_id or uuid4(),
        )
        return SearchProfileResponse.from_domain(profile, run)
    except Exception as error:
        handled = _handle_radar_error(request, error)
        if handled is not None:
            return handled
        raise
