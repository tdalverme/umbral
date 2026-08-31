"""Product surface for listing detail, authorized through the user's runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from sqlalchemy import text

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.application.radar.contracts import ListingDetail, ListingNotAccessible
from umbral.application.radar.service import RadarService
from umbral.infrastructure.db.session import SessionProvider

# OSM category -> frontend PoiCategory (apps/web/src/lib/radar/urban.ts)
_OSM_TO_FRONTEND: dict[str, str | None] = {
    "supermarket": "comercio",
    "convenience": "comercio",
    "pharmacy": "salud",
    "health": "salud",
    "cafe": "cafes",
    "nightlife": "comercio",
    "restaurant": "comercio",
    "bus_stop": "transporte",
    "subway_station": "transporte",
    "train_station": "transporte",
    "green_space": "parques",
    "shopping_mall": "comercio",
    "gym": "deporte",
    "cinema": "cultura",
    "library": "cultura",
    "theatre": "cultura",
    "bicycle_parking": "transporte",
    "school": "educacion",
    "sports_facility": "deporte",
    "museum": "cultura",
    "highway": None,
    "major_road": None,
    "railway": None,
    "subway_line": None,
    "cycleway": None,
}

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


class PoiResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    category: str
    distance_m: int
    geometry: list[float]  # [lng, lat]


class PoisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_id: UUID
    radius_m: int
    count: int
    pois: list[PoiResponse]


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


@router.get(
    "/listings/{listing_id}/pois",
    operation_id="getListingPois",
    response_model=PoisResponse,
    responses={401: {}, 403: {}, 404: {}},
)
async def get_listing_pois(
    request: Request,
    listing_id: UUID,
    radius_m: int = 600,
    limit: int = 50,
    x_correlation_id: UUID | None = Header(default=None),
) -> PoisResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.listing.read")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    # AuthZ: must have access to this listing via a run
    try:
        _radar().get_listing_detail(principal.user_id, listing_id)
    except ListingNotAccessible as error:
        return _problem(request, 403, error.code, str(error))

    radius_m = max(50, min(radius_m, 1200))
    limit = max(1, min(limit, 100))

    # Direct PostGIS query against urban_categories (ingested OSM snapshot)
    provider = SessionProvider(_deps().settings.database_url)
    with provider.session_factory() as session:
        # latest ready snapshot
        snap_row = session.execute(
            text("SELECT id FROM urban_snapshots WHERE status='ready' ORDER BY created_at DESC LIMIT 1")
        ).first()
        if snap_row is None:
            return PoisResponse(listing_id=listing_id, radius_m=radius_m, count=0, pois=[])
        snapshot_id = snap_row[0]
        # listing geometry
        listing_row = session.execute(
            text("SELECT geometry FROM silver_listings WHERE id=:lid AND geometry IS NOT NULL"),
            {"lid": str(listing_id)},
        ).first()
        if listing_row is None or listing_row[0] is None:
            return PoisResponse(listing_id=listing_id, radius_m=radius_m, count=0, pois=[])
        # fetch nearby OSM pois, ordered by distance
        rows = session.execute(
            text(
                """
                SELECT uc.osm_id, uc.category, uc.name, uc.tags,
                       ST_X(uc.geometry::geometry) AS lng,
                       ST_Y(uc.geometry::geometry) AS lat,
                       ST_Distance(sl.geometry::geography, uc.geometry::geography) AS dist
                FROM silver_listings sl
                JOIN urban_categories uc ON uc.snapshot_id = :snap
                WHERE sl.id = :lid
                  AND sl.geometry IS NOT NULL
                  AND uc.geometry IS NOT NULL
                  AND uc.kind = 'poi'
                  AND ST_DWithin(sl.geometry::geography, uc.geometry::geography, :radius)
                ORDER BY dist ASC
                LIMIT :limit
                """
            ),
            {"snap": str(snapshot_id), "lid": str(listing_id), "radius": radius_m, "limit": limit},
        ).all()

    _FALLBACK_NAME: dict[str, str] = {
        "transporte": "Parada",
        "cafes": "Café",
        "educacion": "Escuela",
        "salud": "Salud",
        "comercio": "Comercio",
        "cultura": "Cultura",
        "deporte": "Deporte",
        "parques": "Espacio verde",
    }
    pois: list[PoiResponse] = []
    for osm_id, cat, name, tags, lng, lat, dist in rows:
        frontend_cat = _OSM_TO_FRONTEND.get(str(cat))
        if frontend_cat is None:
            continue
        display_name = name or (tags or {}).get("name") or (tags or {}).get("brand") or (tags or {}).get("operator")
        if not display_name:
            display_name = _FALLBACK_NAME.get(frontend_cat, str(cat))
        else:
            display_name = str(display_name)
        pois.append(
            PoiResponse(
                id=str(osm_id),
                name=str(display_name)[:80],
                category=frontend_cat,
                distance_m=int(round(float(dist))),
                geometry=[float(lng), float(lat)],
            )
        )
    # already sorted by dist, but re-sort after mapping filter
    pois.sort(key=lambda p: p.distance_m)
    return PoisResponse(listing_id=listing_id, radius_m=radius_m, count=len(pois), pois=pois)
