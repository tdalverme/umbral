"""Product surface for the urban signals catalog.

Read-only reference endpoint exposing the available urban signals declared by
the active contract, together with the OpenStreetMap attribution and license
the application is required to show when using this data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.infrastructure.urban.contract_loader import load_urban_contract_published

router = APIRouter(prefix="/api/v1/urban", tags=["Urban"])
_dependencies: RuntimeDependencies | None = None


class UrbanSignalItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    kind: str
    normalized_by: str


class UrbanSignalsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: str
    attribution: str
    license: str
    signals: list[UrbanSignalItem]


def configure_urban_routes(dependencies: RuntimeDependencies) -> None:
    global _dependencies
    _dependencies = dependencies


def _deps() -> RuntimeDependencies:
    if _dependencies is None:
        raise RuntimeError("urban routes were not configured")
    return _dependencies


def _correlation(request: Request) -> UUID:
    value = request.headers.get("X-Correlation-ID")
    try:
        return UUID(value) if value else uuid4()
    except ValueError:
        return uuid4()


def _principal(request: Request, action: str) -> CurrentPrincipal:
    token = request.cookies.get(_deps().settings.session_cookie_name)
    if not token:
        raise IdentityError("auth.session_required", status=401, recovery="sign_in")
    access = _deps().access_control
    principal = access.authorize(
        token,
        action="auth.session.read",
        resource_owner_id=None,
        now=datetime.now(timezone.utc),
        correlation_id=_correlation(request),
    )
    return access.authorize(
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
            "title": "Urban",
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID", str(uuid4())),
            "correlation_id": request.headers.get(
                "X-Correlation-ID", str(uuid4())
            ),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/signals",
    operation_id="getUrbanSignals",
    response_model=UrbanSignalsResponse,
    responses={401: {}, 403: {}},
)
async def get_urban_signals(
    request: Request,
) -> UrbanSignalsResponse | JSONResponse:
    try:
        _principal(request, "product.urban.read")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")

    contract = load_urban_contract_published()
    signals = [
        UrbanSignalItem(
            name=signal.name,
            kind=signal.kind,
            normalized_by=signal.normalized_by,
        )
        for signal in contract.signals
    ]
    return UrbanSignalsResponse(
        contract_version=contract.contract_version,
        attribution=contract.source.attribution,
        license=contract.source.license,
        signals=signals,
    )
