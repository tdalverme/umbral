"""Product surface for immutable feedback and decision-state views."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.feedback.contracts import (
    DecisionItem,
    FeedbackError,
    FeedbackInvalidReason,
    FeedbackNotAccessible,
    FeedbackNotFound,
    FeedbackStateError,
    FeedbackTerminal,
    FeedbackValidationError,
)
from umbral.application.feedback.service import FeedbackService
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError

router = APIRouter(prefix="/api/v1", tags=["Feedback"])
_dependencies: RuntimeDependencies | None = None


class FeedbackRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    search_profile_id: UUID
    listing_id: UUID
    event_type: str
    decision_state: str
    superseded: bool
    noop: bool
    reason_keys: list[str]


class DecisionItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_id: UUID
    decision_state: str
    event_id: UUID
    event_type: str
    reason_keys: list[str]
    created_at: datetime
    total_cost: float | None = None
    neighborhood: str | None = None
    surface_m2: float | None = None
    rooms: int | None = None
    source_id: str | None = None
    url: str | None = None
    geo_precision: str | None = None


class DecisionItemsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search_profile_id: UUID
    items: list[DecisionItemResponse]
    next_after_position: int | None = None


class FeedbackWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    listing_id: UUID
    run_id: UUID | None = None
    event_type: str
    reason_keys: list[str] = Field(default_factory=list)
    free_feedback: str | None = None
    idempotency_key: str = Field(min_length=1, max_length=200)


def configure_feedback_routes(dependencies: RuntimeDependencies) -> None:
    global _dependencies
    _dependencies = dependencies


def _feedback() -> FeedbackService:
    service = _deps().feedback
    if service is None:
        raise RuntimeError("feedback service was not configured")
    return service


def _deps() -> RuntimeDependencies:
    if _dependencies is None:
        raise RuntimeError("feedback routes were not configured")
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
        CurrentPrincipal | None, getattr(request.state, "feedback_principal", None)
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
    request.state.feedback_principal = principal
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
            "title": "Feedback",
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID", str(uuid4())),
            "correlation_id": request.headers.get("X-Correlation-ID", str(uuid4())),
        },
        headers={"Cache-Control": "no-store"},
    )


def _problem_for(error: FeedbackError) -> tuple[int, str, str]:
    if isinstance(error, FeedbackNotFound):
        return 404, error.code, str(error)
    if isinstance(error, FeedbackNotAccessible):
        return 403, error.code, str(error)
    if isinstance(error, (FeedbackTerminal, FeedbackStateError)):
        return 409, error.code, str(error)
    if isinstance(error, FeedbackValidationError):
        return 400, error.code, str(error)
    if isinstance(error, FeedbackInvalidReason):
        return 400, error.code, str(error)
    return 400, error.code, str(error)


def _item_response(item: DecisionItem) -> DecisionItemResponse:
    summary = item.summary
    return DecisionItemResponse(
        listing_id=item.listing_id,
        decision_state=item.decision_state,
        event_id=item.event_id,
        event_type=item.event_type,
        reason_keys=list(item.reason_keys),
        created_at=item.created_at,
        total_cost=summary.total_cost if summary is not None else None,
        neighborhood=summary.neighborhood if summary is not None else None,
        surface_m2=summary.surface_m2 if summary is not None else None,
        rooms=summary.rooms if summary is not None else None,
        source_id=summary.source.source_id if summary is not None else None,
        url=summary.url if summary is not None else None,
        geo_precision=summary.geo_precision if summary is not None else None,
    )


@router.post(
    "/search-profiles/{search_profile_id}/feedback",
    operation_id="recordFeedback",
    response_model=FeedbackRecordResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}, 409: {}},
)
async def record_feedback(
    request: Request,
    search_profile_id: UUID,
    body: FeedbackWriteRequest,
    x_correlation_id: UUID | None = Header(default=None),
) -> FeedbackRecordResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.feedback.write")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        record = _feedback().record_feedback(
            owner_id=principal.user_id,
            profile_id=search_profile_id,
            listing_id=body.listing_id,
            run_id=body.run_id,
            event_type=body.event_type,
            reason_keys=tuple(body.reason_keys),
            free_feedback=body.free_feedback,
            idempotency_key=body.idempotency_key,
            correlation_id=_correlation(request) or uuid4(),
            actor_kind="service",
            actor_id=None,
        )
        return FeedbackRecordResponse(
            event_id=record.event.event_id,
            search_profile_id=search_profile_id,
            listing_id=record.event.listing_id,
            event_type=record.event.event_type,
            decision_state=record.decision_state,
            superseded=record.superseded,
            noop=record.noop,
            reason_keys=[reason.reason_key for reason in record.event.reasons],
        )
    except FeedbackError as error:
        status, code, detail = _problem_for(error)
        return _problem(request, status, code, detail)


@router.get(
    "/search-profiles/{search_profile_id}/decision-items",
    operation_id="listDecisionItems",
    response_model=DecisionItemsResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}},
)
async def list_decision_items(
    request: Request,
    search_profile_id: UUID,
    decision_state: str | None = Query(default=None),
    page_size: int = Query(default=25, ge=1, le=100),
    after_position: int | None = Query(default=None, ge=0),
    x_correlation_id: UUID | None = Header(default=None),
) -> DecisionItemsResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.feedback.read")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        items, next_after = _feedback().list_decision_items(
            owner_id=principal.user_id,
            profile_id=search_profile_id,
            decision_state=decision_state,
            after=after_position,
            limit=page_size,
        )
        return DecisionItemsResponse(
            search_profile_id=search_profile_id,
            items=[_item_response(item) for item in items],
            next_after_position=next_after,
        )
    except FeedbackError as error:
        status, code, detail = _problem_for(error)
        return _problem(request, status, code, detail)
