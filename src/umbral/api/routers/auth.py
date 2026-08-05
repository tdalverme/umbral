"""Private identity HTTP routes; browser access is only through the BFF."""
# ruff: noqa: E501

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.identity.contracts import NEUTRAL_MESSAGE, IdentityError

router = APIRouter(prefix="/api/v1", tags=["Authentication"])
_dependencies: RuntimeDependencies | None = None


class MagicLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)


class MagicLinkConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: UUID
    token_hash: str = Field(min_length=32, max_length=512)


class CurrentSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    roles: tuple[str, ...]
    last_activity_at: datetime


def configure_auth_routes(dependencies: RuntimeDependencies) -> None:
    global _dependencies
    _dependencies = dependencies


def _deps() -> RuntimeDependencies:
    if _dependencies is None:
        raise RuntimeError("auth routes were not configured")
    return _dependencies


def _problem(error: IdentityError, request: Request) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid4()))
    content: dict[str, object] = {
        "type": f"https://umbral.invalid/problems/{error.code}",
        "title": "No se pudo completar el acceso",
        "status": error.status,
        "code": error.code,
        "recovery": error.recovery,
        "request_id": request_id,
        "correlation_id": correlation_id,
    }
    if error.detail:
        content["detail"] = error.detail
    return JSONResponse(
        status_code=error.status,
        media_type="application/problem+json",
        content=content,
        headers={"Cache-Control": "no-store"},
    )


def _check_bff(token: str | None) -> None:
    expected = _deps().settings.bff_token
    if expected and token != expected:
        raise IdentityError("auth.request_invalid", status=400, recovery="none")


@router.post(
    "/auth/magic-link-requests",
    operation_id="requestMagicLink",
    status_code=202,
    response_model=None,
)
async def request_magic_link(
    payload: MagicLinkRequest,
    request: Request,
    x_umbral_bff_token: str | None = Header(default=None, include_in_schema=False),
    x_umbral_origin_fingerprint: str | None = Header(default=None, include_in_schema=False),
    x_correlation_id: UUID | None = Header(default=None),
) -> dict[str, str] | JSONResponse:
    try:
        _check_bff(x_umbral_bff_token)
        result = _deps().identity_access.request_magic_link(
            email=payload.email,
            origin_fingerprint=x_umbral_origin_fingerprint or "local-origin",
            correlation_id=x_correlation_id or uuid4(),
            now=datetime.now(timezone.utc),
        )
        return JSONResponse({"message": result.message}, status_code=202, headers={"Cache-Control": "no-store"})
    except IdentityError as error:
        if error.code == "auth.request_invalid":
            return _problem(error, request)
        return JSONResponse({"message": NEUTRAL_MESSAGE}, status_code=202, headers={"Cache-Control": "no-store"})


@router.post("/auth/magic-link-confirmations", operation_id="confirmMagicLink", status_code=204, response_model=None)
async def confirm_magic_link(
    payload: MagicLinkConfirmation,
    request: Request,
    response: Response,
    x_umbral_bff_token: str | None = Header(default=None, include_in_schema=False),
    x_correlation_id: UUID | None = Header(default=None),
) -> Response | JSONResponse:
    try:
        _check_bff(x_umbral_bff_token)
        result = _deps().identity_access.confirm_magic_link(attempt_id=payload.attempt_id, token_hash=payload.token_hash, now=datetime.now(timezone.utc))
    except IdentityError as error:
        return _problem(error, request)
    response.set_cookie(
        key=_deps().settings.session_cookie_name,
        value=result.token,
        httponly=True,
        secure=_deps().settings.session_secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.get("/auth/session", operation_id="getCurrentSession", response_model=CurrentSession)
async def get_current_session(request: Request, x_umbral_bff_token: str | None = Header(default=None, include_in_schema=False), x_correlation_id: UUID | None = Header(default=None)) -> CurrentSession | JSONResponse:
    try:
        _check_bff(x_umbral_bff_token)
        token = request.cookies.get(_deps().settings.session_cookie_name)
        if not token:
            raise IdentityError("auth.session_required", status=401, recovery="sign_in")
        principal = _deps().access_control.authorize(token, action="auth.session.read", resource_owner_id=None, now=datetime.now(timezone.utc), correlation_id=x_correlation_id)
        return CurrentSession(
            user_id=principal.user_id,
            roles=principal.roles,
            last_activity_at=principal.last_activity_at,
        )
    except IdentityError as error:
        return _problem(error, request)


@router.post("/auth/logout", operation_id="logoutCurrentSession", status_code=204, response_model=None)
async def logout(request: Request, response: Response, x_umbral_bff_token: str | None = Header(default=None, include_in_schema=False), x_correlation_id: UUID | None = Header(default=None)) -> Response | JSONResponse:
    try:
        _check_bff(x_umbral_bff_token)
        token = request.cookies.get(_deps().settings.session_cookie_name)
        if token:
            _deps().identity_access.logout(token, now=datetime.now(timezone.utc), correlation_id=x_correlation_id)
    except IdentityError as error:
        return _problem(error, request)
    response.delete_cookie(_deps().settings.session_cookie_name, path="/")
    response.headers["Cache-Control"] = "private, no-store"
    return response
