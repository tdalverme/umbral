"""RFC 9457 HTTP adaptation of safe domain errors."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import Request
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse, Response

from umbral.domain.errors import ApplicationError, InternalRuntimeError

_PROBLEM_BASE_URL = "https://umbral.invalid/problems/"


def problem_response(request: Request, error: ApplicationError) -> JSONResponse:
    """Return a deliberately minimal problem document without request input."""

    request_id = getattr(request.state, "request_id", str(uuid4()))
    correlation_id = getattr(request.state, "correlation_id", str(uuid4()))
    body: dict[str, Any] = {
        "type": f"{_PROBLEM_BASE_URL}{error.code}",
        "title": error.title,
        "status": error.status,
        "code": error.code,
        "request_id": request_id,
        "correlation_id": correlation_id,
    }
    return JSONResponse(
        status_code=error.status,
        content=body,
        media_type="application/problem+json",
        headers={"Cache-Control": "no-store"},
    )


async def application_error_handler(
    request: Request, error: Exception
) -> JSONResponse:
    """Translate explicitly typed application errors."""

    if isinstance(error, ApplicationError):
        return problem_response(request, error)
    return problem_response(request, InternalRuntimeError())


async def validation_error_handler(
    request: Request, _error: Exception
) -> JSONResponse:
    """Avoid echoing invalid payloads in validation diagnostics."""

    return problem_response(
        request,
        ApplicationError(
            code="request.validation_failed",
            title="Invalid request",
            status=422,
        ),
    )


async def http_error_handler(
    request: Request, error: Exception
) -> JSONResponse:
    """Ensure framework HTTP errors share the safe public envelope."""

    if not isinstance(error, StarletteHTTPException):
        return problem_response(request, InternalRuntimeError())
    return problem_response(
        request,
        ApplicationError(
            code=f"http.status_{error.status_code}",
            title="Request failed",
            status=error.status_code,
        ),
    )


async def unhandled_error_handler(request: Request, _error: Exception) -> Response:
    """Hide unexpected exception messages from clients."""

    return problem_response(request, InternalRuntimeError())
