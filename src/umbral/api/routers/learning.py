"""Product surface for controlled learning proposals (H3.3)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.feedback.contracts import (
    ConfirmationResult,
    FeedbackError,
    FeedbackNotAccessible,
    FeedbackNotFound,
    FeedbackStateError,
    FeedbackValidationError,
    LearningProposal,
    ProposalChange,
    ProposalNotConfirmed,
    ProposalNotFound,
    ProposalNotPending,
)
from umbral.application.feedback.service import FeedbackService
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError

router = APIRouter(prefix="/api/v1", tags=["Learning"])
_dependencies: RuntimeDependencies | None = None


class ProposalChangeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    concept_key: str
    polarity: str
    suggested_weight: float
    suggested_confidence: float
    value: object | None = None


class ProposalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal_id: UUID
    search_profile_id: UUID
    concept_key: str
    policy_version: str
    change: ProposalChangeResponse
    evidence_refs: list[dict[str, object]]
    state: str
    expires_at: datetime
    created_at: datetime


class ProposalsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search_profile_id: UUID
    items: list[ProposalResponse]
    next_after_position: int | None = None


class ProposalWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    change: ProposalChangeBody


class ProposalChangeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = "preference_fact"
    concept_key: str
    polarity: str
    suggested_weight: float = Field(ge=0, le=1)
    suggested_confidence: float = Field(ge=0, le=1)
    value: object | None = None


class ConfirmationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    proposal: ProposalResponse
    applied_profile_version: int
    run_id: UUID | None


def configure_learning_routes(dependencies: RuntimeDependencies) -> None:
    global _dependencies
    _dependencies = dependencies


def _feedback() -> FeedbackService:
    service = _deps().feedback
    if service is None:
        raise RuntimeError("feedback service was not configured")
    return service


def _deps() -> RuntimeDependencies:
    if _dependencies is None:
        raise RuntimeError("learning routes were not configured")
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
        CurrentPrincipal | None, getattr(request.state, "learning_principal", None)
    )
    if cached is not None:
        return cached
    token = request.cookies.get(_deps().settings.session_cookie_name)
    if not token:
        raise IdentityError("auth.session_required", status=401, recovery="sign_in")
    principal = _deps().access_control.authorize(
        token,
        action="product.learning.read",
        resource_owner_id=None,
        now=datetime.now(timezone.utc),
        correlation_id=_correlation(request),
    )
    request.state.learning_principal = principal
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
            "title": "Learning",
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID", str(uuid4())),
            "correlation_id": request.headers.get("X-Correlation-ID", str(uuid4())),
        },
        headers={"Cache-Control": "no-store"},
    )


def _problem_for(error: FeedbackError) -> tuple[int, str, str]:
    if isinstance(error, (ProposalNotFound, FeedbackNotFound)):
        return 404, error.code, str(error)
    if isinstance(error, FeedbackNotAccessible):
        return 403, error.code, str(error)
    if isinstance(error, (ProposalNotConfirmed, ProposalNotPending)):
        return 409, error.code, str(error)
    if isinstance(error, FeedbackStateError):
        return 409, error.code, str(error)
    if isinstance(error, FeedbackValidationError):
        return 400, error.code, str(error)
    return 400, error.code, str(error)


def _proposal_response(proposal: LearningProposal) -> ProposalResponse:
    return ProposalResponse(
        proposal_id=proposal.proposal_id,
        search_profile_id=proposal.profile_id,
        concept_key=proposal.concept_key,
        policy_version=proposal.policy_version,
        change=ProposalChangeResponse(
            kind=proposal.change.kind,
            concept_key=proposal.change.concept_key,
            polarity=proposal.change.polarity,
            suggested_weight=proposal.change.suggested_weight,
            suggested_confidence=proposal.change.suggested_confidence,
            value=proposal.change.value,
        ),
        evidence_refs=[dict(ref) for ref in proposal.evidence_refs],
        state=proposal.state,
        expires_at=proposal.expires_at,
        created_at=proposal.created_at,
    )


def _change(proposal: LearningProposal) -> ProposalResponse:
    return _proposal_response(proposal)


@router.get(
    "/search-profiles/{search_profile_id}/learning-proposals",
    operation_id="listLearningProposals",
    response_model=ProposalsResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}},
)
async def list_learning_proposals(
    request: Request,
    search_profile_id: UUID,
    state: str | None = Query(default=None),
    page_size: int = Query(default=25, ge=1, le=100),
    after_position: int | None = Query(default=None, ge=0),
    x_correlation_id: UUID | None = Header(default=None),
) -> ProposalsResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.learning.read")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        items, next_after = _feedback().list_proposals(
            owner_id=principal.user_id,
            profile_id=search_profile_id,
            state=state,
            after=after_position,
            limit=page_size,
        )
        return ProposalsResponse(
            search_profile_id=search_profile_id,
            items=[_proposal_response(item) for item in items],
            next_after_position=next_after,
        )
    except FeedbackError as error:
        status, code, detail = _problem_for(error)
        return _problem(request, status, code, detail)


@router.put(
    "/search-profiles/{search_profile_id}/learning-proposals/{proposal_id}",
    operation_id="expandLearningProposal",
    response_model=ProposalResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}, 409: {}},
)
async def expand_learning_proposal(
    request: Request,
    search_profile_id: UUID,
    proposal_id: UUID,
    body: ProposalWriteRequest,
    x_correlation_id: UUID | None = Header(default=None),
) -> ProposalResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.learning.write")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        proposal = _feedback().expand_proposal(
            owner_id=principal.user_id,
            profile_id=search_profile_id,
            proposal_id=proposal_id,
            change=ProposalChange(
                kind="preference_fact",
                concept_key=body.change.concept_key,
                polarity=body.change.polarity,
                suggested_weight=body.change.suggested_weight,
                suggested_confidence=body.change.suggested_confidence,
                value=body.change.value,
            ),
            correlation_id=_correlation(request) or uuid4(),
            actor_id=None,
        )
        return _proposal_response(proposal)
    except FeedbackError as error:
        status, code, detail = _problem_for(error)
        return _problem(request, status, code, detail)


@router.post(
    "/search-profiles/{search_profile_id}/learning-proposals/{proposal_id}/confirm",
    operation_id="confirmLearningProposal",
    response_model=ConfirmationResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}, 409: {}},
)
async def confirm_learning_proposal(
    request: Request,
    search_profile_id: UUID,
    proposal_id: UUID,
    x_correlation_id: UUID | None = Header(default=None),
) -> ConfirmationResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.learning.write")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        result: ConfirmationResult = _feedback().confirm_proposal(
            owner_id=principal.user_id,
            profile_id=search_profile_id,
            proposal_id=proposal_id,
            correlation_id=_correlation(request) or uuid4(),
            actor_id=None,
        )
        return ConfirmationResponse(
            proposal=_proposal_response(result.proposal),
            applied_profile_version=result.applied_profile_version,
            run_id=result.run_id,
        )
    except FeedbackError as error:
        status, code, detail = _problem_for(error)
        return _problem(request, status, code, detail)


@router.post(
    "/search-profiles/{search_profile_id}/learning-proposals/{proposal_id}/reject",
    operation_id="rejectLearningProposal",
    response_model=ProposalResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}, 409: {}},
)
async def reject_learning_proposal(
    request: Request,
    search_profile_id: UUID,
    proposal_id: UUID,
    x_correlation_id: UUID | None = Header(default=None),
) -> ProposalResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.learning.write")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        proposal = _feedback().reject_proposal(
            owner_id=principal.user_id,
            profile_id=search_profile_id,
            proposal_id=proposal_id,
            correlation_id=_correlation(request) or uuid4(),
            actor_id=None,
        )
        return _proposal_response(proposal)
    except FeedbackError as error:
        status, code, detail = _problem_for(error)
        return _problem(request, status, code, detail)


@router.post(
    "/search-profiles/{search_profile_id}/learning-proposals/{proposal_id}/undo",
    operation_id="undoLearningProposal",
    response_model=ProposalResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}, 409: {}},
)
async def undo_learning_proposal(
    request: Request,
    search_profile_id: UUID,
    proposal_id: UUID,
    x_correlation_id: UUID | None = Header(default=None),
) -> ProposalResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.learning.write")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        proposal = _feedback().undo_proposal(
            owner_id=principal.user_id,
            profile_id=search_profile_id,
            proposal_id=proposal_id,
            correlation_id=_correlation(request) or uuid4(),
            actor_id=None,
        )
        return _proposal_response(proposal)
    except FeedbackError as error:
        status, code, detail = _problem_for(error)
        return _problem(request, status, code, detail)
