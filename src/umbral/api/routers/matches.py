"""Product surface for persistent recommendation matches of a radar."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.application.radar.contracts import (
    ListingSummary,
    MatchPoint,
    RadarNotAccessible,
    RadarStateError,
    RecommendationItem,
    RecommendationRun,
    RunNotFound,
)
from umbral.application.radar.service import RadarService

router = APIRouter(prefix="/api/v1", tags=["Matches"])
_dependencies: RuntimeDependencies | None = None


class MatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: UUID
    listing_id: UUID
    score: float
    position: int
    contributions: dict[str, object]
    geo_precision: str | None = None
    geometry: tuple[float, float] | None = None
    total_cost: float | None = None
    neighborhood: str | None = None
    surface_m2: float | None = None
    rooms: int | None = None
    source_id: str | None = None
    url: str | None = None

    @classmethod
    def from_domain(
        cls,
        item: RecommendationItem,
        point: MatchPoint | None = None,
        summary: ListingSummary | None = None,
    ) -> "MatchResponse":
        return cls(
            item_id=item.item_id,
            listing_id=item.listing_id,
            score=item.score,
            position=item.position,
            contributions=dict(item.contributions),
            geo_precision=point.geo_precision if point is not None else None,
            geometry=((point.latitude, point.longitude) if point is not None else None),
            total_cost=summary.total_cost if summary is not None else None,
            neighborhood=summary.neighborhood if summary is not None else None,
            surface_m2=summary.surface_m2 if summary is not None else None,
            rooms=summary.rooms if summary is not None else None,
            source_id=summary.source_id if summary is not None else None,
            url=summary.url if summary is not None else None,
        )


class MatchesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search_profile_id: UUID
    run_id: UUID
    run_state: str
    items: list[MatchResponse]
    next_after_position: int | None = None

    @classmethod
    def from_domain(
        cls,
        profile_id: UUID,
        run: RecommendationRun,
        items: tuple[RecommendationItem, ...],
        next_after_position: int | None,
        points: tuple[MatchPoint, ...] = (),
        summaries: tuple[ListingSummary, ...] = (),
    ) -> "MatchesResponse":
        points_by_listing = {point.listing_id: point for point in points}
        summaries_by_listing = {summary.listing_id: summary for summary in summaries}
        return cls(
            search_profile_id=profile_id,
            run_id=run.run_id,
            run_state=run.state,
            items=[
                MatchResponse.from_domain(
                    item,
                    points_by_listing.get(item.listing_id),
                    summaries_by_listing.get(item.listing_id),
                )
                for item in items
            ],
            next_after_position=next_after_position,
        )


def configure_matches_routes(dependencies: RuntimeDependencies) -> None:
    global _dependencies
    _dependencies = dependencies


def _radar() -> RadarService:
    service = _deps().radar
    if service is None:
        raise RuntimeError("radar service was not configured")
    return service


def _deps() -> RuntimeDependencies:
    if _dependencies is None:
        raise RuntimeError("matches routes were not configured")
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
            "title": "Matches",
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID", str(uuid4())),
            "correlation_id": request.headers.get("X-Correlation-ID", str(uuid4())),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/search-profiles/{search_profile_id}/matches",
    operation_id="listMatches",
    response_model=MatchesResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}},
)
async def list_matches(
    request: Request,
    search_profile_id: UUID,
    run_id: UUID | None = None,
    page_size: int = Query(default=25, ge=1, le=100),
    after_position: int | None = Query(default=None, ge=0),
    x_correlation_id: UUID | None = Header(default=None),
) -> MatchesResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.matches.read")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        page = _radar().get_matches(
            owner_id=principal.user_id,
            profile_id=search_profile_id,
            run_id=run_id,
            after_position=after_position,
            limit=page_size,
        )
        return MatchesResponse.from_domain(
            search_profile_id,
            page.run,
            page.items,
            page.next_after_position,
            page.points,
            page.summaries,
        )
    except RunNotFound as error:
        return _problem(request, 404, error.code, str(error))
    except RadarNotAccessible as error:
        return _problem(request, 403, error.code, str(error))
    except RadarStateError as error:
        return _problem(request, 400, error.code, str(error))
