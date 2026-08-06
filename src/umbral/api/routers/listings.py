"""Product surface for listing detail, authorized through the user's runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.application.radar.contracts import ListingDetail, ListingNotAccessible
from umbral.application.radar.service import RadarService

router = APIRouter(prefix="/api/v1", tags=["Listings"])
_dependencies: RuntimeDependencies | None = None


class KnownChangeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    change_type: str
    field: str
    before: object
    after: object


class ListingDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_id: UUID
    source_id: str
    url: str | None = None
    neighborhood: str | None = None
    geo_precision: str
    total_cost: float
    price_value: float
    price_currency: str
    expenses_value: float | None = None
    surface_m2: float | None = None
    rooms: int | None = None
    bedrooms: int | None = None
    floor: int | None = None
    property_type: str
    amenities: list[str]
    description_text: str | None = None
    normalization_errors: list[str]
    known_changes: list[KnownChangeModel]

    @classmethod
    def from_domain(cls, detail: ListingDetail) -> "ListingDetailResponse":
        return cls(
            listing_id=detail.listing_id,
            source_id=detail.source_id,
            url=detail.url,
            neighborhood=detail.neighborhood,
            geo_precision=detail.geo_precision,
            total_cost=detail.total_cost,
            price_value=detail.price_value,
            price_currency=detail.price_currency,
            expenses_value=detail.expenses_value,
            surface_m2=detail.surface_m2,
            rooms=detail.rooms,
            bedrooms=detail.bedrooms,
            floor=detail.floor,
            property_type=detail.property_type,
            amenities=list(detail.amenities),
            description_text=detail.description_text,
            normalization_errors=list(detail.normalization_errors),
            known_changes=[
                KnownChangeModel(
                    change_type=str(change.get("change_type")),
                    field=str(change.get("field")),
                    before=change.get("before"),
                    after=change.get("after"),
                )
                for change in detail.known_changes
            ],
        )


def configure_listings_routes(dependencies: RuntimeDependencies) -> None:
    global _dependencies
    _dependencies = dependencies


def _radar() -> RadarService:
    service = _deps().radar
    if service is None:
        raise RuntimeError("radar service was not configured")
    return service


def _deps() -> RuntimeDependencies:
    if _dependencies is None:
        raise RuntimeError("listings routes were not configured")
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
            "title": "Listings",
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID", str(uuid4())),
            "correlation_id": request.headers.get("X-Correlation-ID", str(uuid4())),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/listings/{listing_id}",
    operation_id="getListingDetail",
    response_model=ListingDetailResponse,
    responses={401: {}, 403: {}, 404: {}},
)
async def get_listing_detail(
    request: Request,
    listing_id: UUID,
    x_correlation_id: UUID | None = Header(default=None),
) -> ListingDetailResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.listing.read")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        detail = _radar().get_listing_detail(principal.user_id, listing_id)
        return ListingDetailResponse.from_domain(detail)
    except ListingNotAccessible as error:
        return _problem(request, 403, error.code, str(error))
