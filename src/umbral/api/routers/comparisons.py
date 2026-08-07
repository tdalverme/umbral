"""Product surface for structured comparison and the persistent shortlist (P1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.application.scoring.contracts import (
    Comparison,
    ScoringError,
)
from umbral.application.scoring.service import ScoringService

router = APIRouter(prefix="/api/v1", tags=["Comparisons"])
_dependencies: RuntimeDependencies | None = None


class ComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_ids: list[UUID]


class DimensionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    key: str
    label: str
    concept: str | None = None


class CellResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_id: UUID
    dimension_key: str
    value: object
    state: str
    missing: bool
    evidence_refs: list[dict[str, object]] = []


class ComparisonResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search_profile_id: UUID
    run_id: UUID
    score_version: str
    limit: int
    listings: list[dict[str, object]]
    dimensions: list[DimensionResponse]
    cells: list[CellResponse]

    @classmethod
    def from_domain(cls, comparison: Comparison) -> "ComparisonResponse":
        return cls(
            search_profile_id=comparison.search_profile_id,
            run_id=comparison.run_id,
            score_version=comparison.score_version,
            limit=comparison.limit,
            listings=[dict(item) for item in comparison.listings],
            dimensions=[
                DimensionResponse(
                    kind=dimension.kind,
                    key=dimension.key,
                    label=dimension.label,
                    concept=dimension.concept,
                )
                for dimension in comparison.dimensions
            ],
            cells=[
                CellResponse(
                    listing_id=cell.listing_id,
                    dimension_key=cell.dimension_key,
                    value=cell.value,
                    state=cell.state,
                    missing=cell.missing,
                    evidence_refs=[dict(ref) for ref in cell.evidence_refs],
                )
                for cell in comparison.cells
            ],
        )


class ShortlistResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search_profile_id: UUID
    listing_ids: list[UUID]


class ShortlistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_ids: list[UUID]


def configure_comparisons_routes(dependencies: RuntimeDependencies) -> None:
    global _dependencies
    _dependencies = dependencies


def _scoring() -> ScoringService:
    service = _deps().scoring
    if service is None:
        raise RuntimeError("scoring service was not configured")
    return service


def _deps() -> RuntimeDependencies:
    if _dependencies is None:
        raise RuntimeError("comparisons routes were not configured")
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
        CurrentPrincipal | None, getattr(request.state, "comparison_principal", None)
    )
    if cached is not None:
        return cached
    token = request.cookies.get(_deps().settings.session_cookie_name)
    if not token:
        raise IdentityError("auth.session_required", status=401, recovery="sign_in")
    principal = _deps().access_control.authorize(
        token,
        action="product.comparison.read",
        resource_owner_id=None,
        now=datetime.now(timezone.utc),
        correlation_id=_correlation(request),
    )
    request.state.comparison_principal = principal
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
            "title": "Comparisons",
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID", str(uuid4())),
            "correlation_id": request.headers.get("X-Correlation-ID", str(uuid4())),
        },
        headers={"Cache-Control": "no-store"},
    )


def _problem_for(error: ScoringError) -> tuple[int, str, str]:
    if error.code == "comparison.not_accessible":
        return 403, error.code, str(error)
    if error.code == "scoring.not_found":
        return 404, error.code, str(error)
    if error.code == "explanation_unavailable":
        return 400, error.code, str(error)
    return 400, error.code, str(error)


@router.post(
    "/search-profiles/{search_profile_id}/comparisons",
    operation_id="createComparison",
    response_model=ComparisonResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}},
)
async def create_comparison(
    request: Request,
    search_profile_id: UUID,
    body: ComparisonRequest,
    x_correlation_id: UUID | None = Header(default=None),
) -> ComparisonResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.comparison.read")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        comparison = _scoring().build_comparison(
            owner_id=principal.user_id,
            profile_id=search_profile_id,
            listing_ids=tuple(body.listing_ids),
        )
        return ComparisonResponse.from_domain(comparison)
    except ScoringError as error:
        status, code, detail = _problem_for(error)
        return _problem(request, status, code, detail)


@router.get(
    "/search-profiles/{search_profile_id}/comparison-shortlist",
    operation_id="getComparisonShortlist",
    response_model=ShortlistResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}},
)
async def get_shortlist(
    request: Request,
    search_profile_id: UUID,
    x_correlation_id: UUID | None = Header(default=None),
) -> ShortlistResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.comparison.read")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        listing_ids = _scoring().get_shortlist(
            owner_id=principal.user_id, profile_id=search_profile_id
        )
        return ShortlistResponse(
            search_profile_id=search_profile_id, listing_ids=list(listing_ids)
        )
    except ScoringError as error:
        status, code, detail = _problem_for(error)
        return _problem(request, status, code, detail)


@router.put(
    "/search-profiles/{search_profile_id}/comparison-shortlist",
    operation_id="setComparisonShortlist",
    response_model=ShortlistResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}},
)
async def set_shortlist(
    request: Request,
    search_profile_id: UUID,
    body: ShortlistRequest,
    x_correlation_id: UUID | None = Header(default=None),
) -> ShortlistResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.comparison.write")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        listing_ids = _scoring().set_shortlist(
            owner_id=principal.user_id,
            profile_id=search_profile_id,
            listing_ids=tuple(body.listing_ids),
            correlation_id=_correlation(request) or uuid4(),
        )
        return ShortlistResponse(
            search_profile_id=search_profile_id, listing_ids=list(listing_ids)
        )
    except ScoringError as error:
        status, code, detail = _problem_for(error)
        return _problem(request, status, code, detail)
