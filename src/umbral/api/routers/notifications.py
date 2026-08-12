"""Product surface for notification preferences, inbox and unsubscribe (H5)."""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.application.notifications.contracts import (
    NotificationPreferences,
    PlannerValidationError,
)

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])
_dependencies: RuntimeDependencies | None = None


class PreferencesBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_enabled: bool = True
    inbox_enabled: bool = True
    timezone: str = "America/Argentina/Buenos_Aires"
    quiet_hours_start: str = "22:00"
    quiet_hours_end: str = "08:00"
    digest_enabled: bool = True
    digest_local_hour: int = Field(default=9, ge=0, le=23)
    score_threshold: float = Field(default=0.6, ge=0, le=1)
    state: str = "active"
    _STATE_VALUES = {"active", "paused", "disabled"}

    @field_validator("state")
    @classmethod
    def _state(cls, value: str) -> str:
        if value not in cls._STATE_VALUES:
            raise ValueError("invalid state")
        return value

    @field_validator("quiet_hours_start", "quiet_hours_end")
    @classmethod
    def _clock(cls, value: str) -> str:
        try:
            hour, minute = value.split(":")
            time(int(hour), int(minute))
        except ValueError as exc:
            raise ValueError("invalid time") from exc
        return value


class PreferencesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_enabled: bool
    inbox_enabled: bool
    timezone: str
    quiet_hours_start: str
    quiet_hours_end: str
    digest_enabled: bool
    digest_local_hour: int
    score_threshold: float
    state: str
    version: int


class InboxItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_id: UUID
    reason_code: str
    trigger: str
    read: bool
    created_at: datetime


class InboxResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[InboxItemResponse]


class InboxMarkReadBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    read: bool


class UnsubscribeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=1, max_length=500)


def configure_notifications_routes(dependencies: RuntimeDependencies) -> None:
    global _dependencies
    _dependencies = dependencies


def _deps() -> RuntimeDependencies:
    if _dependencies is None:
        raise RuntimeError("notifications routes were not configured")
    return _dependencies


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


def _correlation(request: Request) -> UUID:
    value = request.headers.get("X-Correlation-ID")
    try:
        return UUID(value) if value else uuid4()
    except ValueError:
        return uuid4()


def _problem(request: Request, status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": f"https://umbral.invalid/problems/{code}",
            "title": "Notifications",
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID", str(uuid4())),
            "correlation_id": request.headers.get("X-Correlation-ID", str(uuid4())),
        },
        headers={"Cache-Control": "no-store"},
    )


def _prefs_response(prefs: NotificationPreferences) -> PreferencesResponse:
    return PreferencesResponse(
        email_enabled=prefs.email_enabled,
        inbox_enabled=prefs.inbox_enabled,
        timezone=prefs.timezone,
        quiet_hours_start=prefs.quiet_hours_start.strftime("%H:%M"),
        quiet_hours_end=prefs.quiet_hours_end.strftime("%H:%M"),
        digest_enabled=prefs.digest_enabled,
        digest_local_hour=prefs.digest_local_hour,
        score_threshold=prefs.score_threshold,
        state=prefs.state,
        version=prefs.version,
    )


@router.get("/preferences", response_model=None)
async def get_preferences(
    request: Request,
) -> PreferencesResponse | JSONResponse:
    principal = _principal(request, "product.notifications.preferences.read")
    services = _deps().notifications
    if services is None:
        raise IdentityError("auth.forbidden", status=403, recovery="none")
    search_id = _require_search(request, principal, services)
    prefs = services.preferences.get(  # type: ignore[attr-defined]
        user_id=principal.user_id, search_profile_id=search_id
    )
    return _prefs_response(prefs)


@router.put("/preferences", response_model=None)
async def put_preferences(
    request: Request, body: PreferencesBody
) -> PreferencesResponse | JSONResponse:
    principal = _principal(request, "product.notifications.preferences.write")
    services = _deps().notifications
    if services is None:
        raise IdentityError("auth.forbidden", status=403, recovery="none")
    search_id = _require_search(request, principal, services)
    start_hour, start_min = body.quiet_hours_start.split(":")
    end_hour, end_min = body.quiet_hours_end.split(":")
    prefs = NotificationPreferences(
        email_enabled=body.email_enabled,
        inbox_enabled=body.inbox_enabled,
        timezone=body.timezone,
        quiet_hours_start=time(int(start_hour), int(start_min)),
        quiet_hours_end=time(int(end_hour), int(end_min)),
        digest_enabled=body.digest_enabled,
        digest_local_hour=body.digest_local_hour,
        score_threshold=body.score_threshold,
        state=body.state,  # type: ignore[arg-type]
    )
    try:
        updated = services.preferences.update(  # type: ignore[attr-defined]
            user_id=principal.user_id,
            search_profile_id=search_id,
            preferences=prefs,
            now=datetime.now(timezone.utc),
            correlation_id=_correlation(request),
        )
    except PlannerValidationError as exc:
        return _problem(
            request,
            422,
            "notifications.preferences_invalid",
            str(exc.reason),
        )
    return _prefs_response(updated)


@router.get("/inbox", response_model=None)
async def get_inbox(
    request: Request,
    page_size: int = 20,
) -> InboxResponse | JSONResponse:
    principal = _principal(request, "product.notifications.inbox.read")
    services = _deps().notifications
    if services is None:
        raise IdentityError("auth.forbidden", status=403, recovery="none")
    items = services.inbox.list_for_user(  # type: ignore[attr-defined]
        user_id=principal.user_id, limit=max(1, min(page_size, 50))
    )
    return InboxResponse(
        items=[
            InboxItemResponse(
                decision_id=UUID(str(item["decision_id"])),
                reason_code=str(item.get("reason_code", "")),
                trigger=str(item.get("trigger", "")),
                read=item.get("read_at") is not None,
                created_at=cast(datetime, item["created_at"]),
            )
            for item in items
        ]
    )


@router.patch("/inbox/{decision_id}", response_model=None)
async def patch_inbox(
    request: Request, decision_id: UUID, body: InboxMarkReadBody
) -> InboxItemResponse | JSONResponse:
    principal = _principal(request, "product.notifications.inbox.write")
    services = _deps().notifications
    if services is None:
        raise IdentityError("auth.forbidden", status=403, recovery="none")
    updated = services.inbox.mark_read(  # type: ignore[attr-defined]
        user_id=principal.user_id,
        decision_id=decision_id,
        correlation_id=_correlation(request),
    )
    if not updated:
        return _problem(request, 404, "notifications.item_not_found", "not found")
    return InboxItemResponse(
        decision_id=decision_id,
        reason_code="",
        trigger="",
        read=body.read,
        created_at=datetime.now(timezone.utc),
    )


@router.post("/unsubscribe", status_code=204)
async def unsubscribe(request: Request, body: UnsubscribeBody) -> JSONResponse:
    settings = _deps().settings
    services = _deps().notifications
    if services is None:
        raise IdentityError("auth.forbidden", status=403, recovery="none")
    from umbral.application.notifications.preferences import (
        verify_unsubscribe_token,
    )

    token = body.token
    secret = settings.identity_fingerprint_key.encode()
    user_id, search_id = _token_subject(token)
    if user_id is None or search_id is None:
        return _problem(request, 422, "notifications.token_invalid", "invalid token")
    current = services.preferences.get(  # type: ignore[attr-defined]
        user_id=user_id, search_profile_id=search_id
    )
    version = current.version if current is not None else 1
    if not verify_unsubscribe_token(
        secret=secret,
        token=token,
        user_id=user_id,
        search_profile_id=search_id,
        version=version,
        now=datetime.now(timezone.utc),
    ):
        return _problem(
            request, 422, "notifications.token_expired", "expired or reused"
        )
    disabled = NotificationPreferences(
        email_enabled=False,
        inbox_enabled=False,
        state="disabled",
        version=version + 1,
    )
    services.preferences.update(  # type: ignore[attr-defined]
        user_id=user_id,
        search_profile_id=search_id,
        preferences=disabled,
        now=datetime.now(timezone.utc),
        correlation_id=_correlation(request),
    )
    return JSONResponse(status_code=204, content=None)


def _token_subject(token: str) -> tuple[UUID | None, UUID | None]:
    try:
        payload = token.rsplit(".", 1)[0]
        parts = payload.split("|")
        if len(parts) != 4:
            return None, None
        return UUID(parts[0]), UUID(parts[1])
    except ValueError:
        return None, None


def _require_search(
    request: Request, principal: CurrentPrincipal, services: object
) -> UUID:
    # Preferences are per search profile; the active search is resolved from
    # the session's search context when available, else the user's first
    # active profile.
    search_id = getattr(principal, "search_profile_id", None)
    if isinstance(search_id, UUID):
        return search_id
    profiles = services.profiles.list_active_profiles()  # type: ignore[attr-defined]
    for profile in profiles:
        if profile.get("owner_id") == principal.user_id:
            return UUID(str(profile["search_profile_id"]))
    raise IdentityError("auth.forbidden", status=403, recovery="none")
