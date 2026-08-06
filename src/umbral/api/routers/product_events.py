"""Product surface for validated client-emitted product events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.application.radar.contracts import (
    RadarNotAccessible,
    RadarValidationError,
)
from umbral.application.radar.service import RadarService

router = APIRouter(prefix="/api/v1", tags=["Product Events"])
_dependencies: RuntimeDependencies | None = None


class ProductEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str
    payload: dict[str, object]


class ProductEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    event_type: str
    event_version: int
    occurred_at: datetime


def configure_product_events_routes(dependencies: RuntimeDependencies) -> None:
    global _dependencies
    _dependencies = dependencies


def _radar() -> RadarService:
    service = _deps().radar
    if service is None:
        raise RuntimeError("radar service was not configured")
    return service


def _deps() -> RuntimeDependencies:
    if _dependencies is None:
        raise RuntimeError("product events routes were not configured")
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


def _problem(request: Request, status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": f"https://umbral.invalid/problems/{code}",
            "title": "Product Events",
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID", str(uuid4())),
            "correlation_id": request.headers.get("X-Correlation-ID", str(uuid4())),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/product-events",
    operation_id="emitProductEvent",
    status_code=201,
    response_model=ProductEventResponse,
    responses={400: {}, 401: {}, 403: {}, 422: {}},
)
async def emit_product_event(
    request: Request,
    body: ProductEventRequest,
    x_correlation_id: UUID | None = Header(default=None),
) -> ProductEventResponse | JSONResponse:
    try:
        principal = _principal(request)
        _deps().access_control.authorize(
            request.cookies.get(_deps().settings.session_cookie_name) or "",
            action="product.events.emit",
            resource_owner_id=None,
            now=datetime.now(timezone.utc),
            correlation_id=_correlation(request),
        )
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")

    profile_id = body.payload.get("search_profile_id")
    if isinstance(profile_id, str):
        try:
            parsed = UUID(profile_id)
        except ValueError:
            parsed = None
        if parsed is not None:
            try:
                _radar().get_profile(principal.user_id, parsed)
            except RadarNotAccessible:
                return _problem(
                    request, 403, "radar.not_accessible", "profile not accessible"
                )

    try:
        event = _radar().record_client_event(
            event_type=body.event_type,
            payload=body.payload,
            actor_id=principal.user_id,
            correlation_id=x_correlation_id or uuid4(),
        )
        return ProductEventResponse(
            event_id=event.event_id,
            event_type=event.event_type,
            event_version=event.event_version,
            occurred_at=event.occurred_at,
        )
    except RadarValidationError as error:
        return _problem(
            request, 400, "radar.event_invalid", ",".join(error.error_codes)
        )
    except RadarNotAccessible:
        return _problem(request, 403, "radar.not_accessible", "profile not accessible")
