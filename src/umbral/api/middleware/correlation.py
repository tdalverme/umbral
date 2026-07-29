"""Request and correlation identifier middleware."""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from umbral.api.errors import problem_response
from umbral.domain.errors import InternalRuntimeError


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Attach one server request ID and a valid operation correlation ID."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request.state.request_id = str(uuid4())
        request.state.correlation_id = _correlation_id(
            request.headers.get("X-Correlation-ID")
        )
        try:
            response = await call_next(request)
        except Exception:
            response = problem_response(request, InternalRuntimeError())
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        return response


def _correlation_id(value: str | None) -> str:
    if value is None:
        return str(uuid4())
    try:
        return str(UUID(value))
    except ValueError:
        return str(uuid4())
