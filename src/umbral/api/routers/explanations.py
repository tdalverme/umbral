"""Product surface for deterministic explanations of recommendation runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.application.scoring.contracts import (
    Explanation,
    ExplanationUnavailable,
    ScoringError,
    ScoringNotAccessible,
    ScoringNotFound,
    ScoringStateError,
)
from umbral.application.scoring.service import ScoringService

router = APIRouter(prefix="/api/v1", tags=["Explanations"])
_dependencies: RuntimeDependencies | None = None


class ReasonResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_key: str
    state: str
    score: float
    confidence: float
    contribution: float
    evidence_level: str
    reason_code: str
    evidence_refs: list[dict[str, object]]
    text: str


class RiskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_key: str
    state: str
    reason_code: str
    text: str


class ExplanationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search_profile_id: UUID
    run_id: UUID
    listing_id: UUID
    score_version: str
    score: float
    confidence: float
    reasons: list[ReasonResponse]
    risks: list[RiskResponse]
    missing_data: list[str]
    satisfied_filters: list[str]
    profile_snapshot: dict[str, object]
    feature_snapshot: dict[str, object]

    @classmethod
    def from_domain(cls, explanation: Explanation) -> "ExplanationResponse":
        return cls(
            search_profile_id=explanation.search_profile_id,
            run_id=explanation.run_id,
            listing_id=explanation.listing_id,
            score_version=explanation.score_version,
            score=explanation.score,
            confidence=explanation.confidence,
            reasons=[
                ReasonResponse(
                    criterion_key=reason.criterion_key,
                    state=reason.state,
                    score=reason.score,
                    confidence=reason.confidence,
                    contribution=reason.contribution,
                    evidence_level=reason.evidence_level,
                    reason_code=reason.reason_code,
                    evidence_refs=[dict(ref) for ref in reason.evidence_refs],
                    text=reason.text,
                )
                for reason in explanation.reasons
            ],
            risks=[
                RiskResponse(
                    criterion_key=risk.criterion_key,
                    state=risk.state,
                    reason_code=risk.reason_code,
                    text=risk.text,
                )
                for risk in explanation.risks
            ],
            missing_data=list(explanation.missing_data),
            satisfied_filters=list(explanation.satisfied_filters),
            profile_snapshot=dict(explanation.profile_snapshot),
            feature_snapshot=dict(explanation.feature_snapshot),
        )


class ExplanationsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search_profile_id: UUID
    run_id: UUID
    run_state: str
    items: list[ExplanationResponse]
    next_after_position: int | None = None


def configure_explanations_routes(dependencies: RuntimeDependencies) -> None:
    global _dependencies
    _dependencies = dependencies


def _scoring() -> ScoringService:
    service = _deps().scoring
    if service is None:
        raise RuntimeError("scoring service was not configured")
    return service


def _deps() -> RuntimeDependencies:
    if _dependencies is None:
        raise RuntimeError("explanations routes were not configured")
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
        CurrentPrincipal | None, getattr(request.state, "scoring_principal", None)
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
    request.state.scoring_principal = principal
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
            "title": "Explanations",
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID", str(uuid4())),
            "correlation_id": request.headers.get("X-Correlation-ID", str(uuid4())),
        },
        headers={"Cache-Control": "no-store"},
    )


def _problem_for(error: ScoringError) -> tuple[int, str, str]:
    if isinstance(error, ExplanationUnavailable):
        return 404, error.code, str(error)
    if isinstance(error, ScoringNotFound):
        return 404, error.code, str(error)
    if isinstance(error, ScoringNotAccessible):
        return 403, error.code, str(error)
    if isinstance(error, ScoringStateError):
        return 400, error.code, str(error)
    return 400, error.code, str(error)


@router.get(
    "/search-profiles/{search_profile_id}/explanations/{listing_id}",
    operation_id="getExplanation",
    response_model=ExplanationResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}},
)
async def get_explanation(
    request: Request,
    search_profile_id: UUID,
    listing_id: UUID,
    run_id: UUID | None = None,
    x_correlation_id: UUID | None = Header(default=None),
) -> ExplanationResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.explanation.read")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        explanation = _scoring().get_explanation(
            owner_id=principal.user_id,
            profile_id=search_profile_id,
            run_id=run_id or _latest_run(request, principal.user_id, search_profile_id),
            listing_id=listing_id,
        )
        return ExplanationResponse.from_domain(explanation)
    except ScoringError as error:
        status, code, detail = _problem_for(error)
        return _problem(request, status, code, detail)


@router.get(
    "/search-profiles/{search_profile_id}/explanations",
    operation_id="listExplanations",
    response_model=ExplanationsResponse,
    responses={400: {}, 401: {}, 403: {}, 404: {}},
)
async def list_explanations(
    request: Request,
    search_profile_id: UUID,
    run_id: UUID | None = None,
    page_size: int = Query(default=25, ge=1, le=100),
    after_position: int | None = Query(default=None, ge=0),
    x_correlation_id: UUID | None = Header(default=None),
) -> ExplanationsResponse | JSONResponse:
    del x_correlation_id
    try:
        principal = _require(request, "product.explanation.read")
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    try:
        resolved_run = run_id or _latest_run(
            request, principal.user_id, search_profile_id
        )
        items = _scoring().list_explanations(
            owner_id=principal.user_id,
            profile_id=search_profile_id,
            run_id=resolved_run,
            after_position=after_position,
            limit=page_size,
        )
        next_after = None
        if len(items) == page_size:
            next_after = (after_position or 0) + len(items)
        return ExplanationsResponse(
            search_profile_id=search_profile_id,
            run_id=resolved_run,
            run_state="succeeded",
            items=[ExplanationResponse.from_domain(item) for item in items],
            next_after_position=next_after,
        )
    except ScoringError as error:
        status, code, detail = _problem_for(error)
        return _problem(request, status, code, detail)


def _latest_run(request: Request, owner_id: UUID, profile_id: UUID) -> UUID:
    service = _deps().radar
    if service is None:
        raise ScoringNotFound("radar service is not configured")
    run = service.latest_run_of(service.get_profile(owner_id, profile_id))
    if run is None:
        raise ScoringNotFound(f"no published run for profile: {profile_id}")
    return run.run_id
