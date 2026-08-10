"""Read-only agent ops dashboard (UM-H4-030, R-10).

Internal operator surface: aggregates over the run registry and eval suites,
0 PII, 0 mutations. The web reaches this only through the BFF.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, cast
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from umbral.application.agent_ops.service import OpsOverviewService
from umbral.application.identity.contracts import IdentityError

router = APIRouter(prefix="/api/v1", tags=["agent-ops"])

_dependencies: Any = None


def configure_agent_ops_routes(dependencies: Any) -> None:
    global _dependencies
    _dependencies = dependencies


def _deps() -> Any:
    if _dependencies is None:
        raise RuntimeError("agent ops routes were not configured")
    return _dependencies


def _ops() -> OpsOverviewService:
    service = _deps().ops_overview
    if service is None:
        raise RuntimeError("agent ops service was not configured")
    return cast(OpsOverviewService, service)


def _correlation(request: Request) -> str:
    return request.headers.get("X-Correlation-ID", str(uuid4()))


def _principal(request: Request) -> object:
    token = request.cookies.get(_deps().settings.session_cookie_name)
    if not token:
        raise IdentityError("auth.session_required", status=401, recovery="sign_in")
    return cast(
        object,
        _deps().access_control.authorize(
            token,
            action="ops.agent.read",
            resource_owner_id=None,
            now=datetime.now(timezone.utc),
            correlation_id=None,
        ),
    )


def _problem(request: Request, status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": f"https://umbral.invalid/problems/{code}",
            "title": "Agent Ops",
            "status": status,
            "code": code,
            "detail": detail,
            "request_id": request.headers.get("X-Request-ID", str(uuid4())),
            "correlation_id": _correlation(request),
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/agent/ops/overview",
    operation_id="agentOpsOverview",
    responses={401: {}, 403: {}},
)
async def agent_ops_overview(request: Request) -> JSONResponse:
    try:
        _principal(request)
    except IdentityError as error:
        return _problem(request, error.status, error.code, error.recovery or "")
    report = _ops().overview()
    payload = asdict(report)
    payload["data_as_of"] = report.data_as_of.isoformat()
    return JSONResponse(
        status_code=200,
        media_type="application/json",
        content=payload,
        headers={"Cache-Control": "no-store"},
    )
