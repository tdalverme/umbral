"""API composition root for the foundation runtime."""
# ruff: noqa: E501

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from starlette.exceptions import HTTPException as StarletteHTTPException

from umbral.api.dependencies import build_runtime_dependencies
from umbral.api.errors import (
    application_error_handler,
    http_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from umbral.api.middleware.correlation import CorrelationMiddleware
from umbral.api.routers.auth import configure_auth_routes
from umbral.api.routers.auth import router as auth_router
from umbral.api.routers.email_webhooks import router as email_webhook_router
from umbral.api.routers.runtime import configure_runtime_routes
from umbral.api.routers.runtime import router as runtime_router
from umbral.domain.errors import ApplicationError
from umbral.infrastructure.observability.runtime import (
    initialize_observability,
    shutdown_observability,
)
from umbral.infrastructure.runtime.heartbeat import HEARTBEAT_INTERVAL_SECONDS

_RUNTIME_DESCRIPTION = (
    "Foundation operational contract. Product resources will be added below "
    "/api/v1 without changing these side-effect-free probes."
)
_ENVIRONMENT_ACCESS_DESCRIPTION = (
    "Environment-level operator or service identity. It is not a product "
    "user session or product authorization contract."
)
_CORRELATION_DESCRIPTION = (
    "UUID for a multi-step operation. A valid value is preserved; when absent "
    "the runtime generates one."
)


def _response_headers(*, include_retry_after: bool = False) -> dict[str, Any]:
    headers: dict[str, Any] = {
        "Cache-Control": {"schema": {"type": "string", "const": "no-store"}},
        "X-Request-ID": {"$ref": "#/components/headers/RequestId"},
        "X-Correlation-ID": {"$ref": "#/components/headers/CorrelationId"},
    }
    if include_retry_after:
        headers["Retry-After"] = {
            "schema": {"type": "integer", "minimum": 1, "maximum": 60}
        }
    return headers


def _problem_response(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "headers": {
            "X-Request-ID": {"$ref": "#/components/headers/RequestId"},
            "X-Correlation-ID": {"$ref": "#/components/headers/CorrelationId"},
        },
        "content": {
            "application/problem+json": {
                "schema": {"$ref": "#/components/schemas/Problem"}
            }
        },
    }


def _apply_runtime_openapi_contract(document: dict[str, Any]) -> None:
    """Add gateway contract metadata without changing runtime authorization."""

    document["info"]["description"] = _RUNTIME_DESCRIPTION
    document["servers"] = [
        {"url": "http://127.0.0.1:8000", "description": "Local API"}
    ]
    document["tags"] = [{"name": "Runtime"}]
    document["security"] = [{"environmentAccess": []}]

    components = document.setdefault("components", {})
    components["securitySchemes"] = {
        "environmentAccess": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": _ENVIRONMENT_ACCESS_DESCRIPTION,
        }
    }
    components["parameters"] = {
        "CorrelationId": {
            "name": "X-Correlation-ID",
            "in": "header",
            "required": False,
            "description": _CORRELATION_DESCRIPTION,
            "schema": {"type": "string", "format": "uuid"},
        }
    }
    components["headers"] = {
        "RequestId": {
            "description": "Server-generated UUID for this request",
            "schema": {"type": "string", "format": "uuid"},
        },
        "CorrelationId": {
            "description": "Preserved or server-generated operation UUID",
            "schema": {"type": "string", "format": "uuid"},
        },
    }
    components["responses"] = {
        "Unauthorized": _problem_response("Missing or invalid environment identity"),
        "Forbidden": _problem_response(
            "Valid environment identity without access to this environment"
        ),
    }

    path_metadata = {
        "/health": {
            "summary": "Confirm that the current process can respond",
            "description": (
                "Executes no dependency check and creates no durable connection, "
                "record, job or object. This is the only operation that may "
                "bypass the environment access control."
            ),
        },
        "/ready": {
            "summary": "Report readiness for one runtime surface",
            "description": (
                "Returns only allowlisted dependency names, state, criticality "
                "and stable codes. A degraded response remains HTTP-ready but is "
                "rejected by the release gate. A critical failure returns 503."
            ),
        },
        "/version": {
            "summary": "Identify the exact executing release and artifact",
        },
    }

    for path, metadata in path_metadata.items():
        operation = document["paths"][path]["get"]
        operation.update(metadata)
        operation["parameters"] = [{"$ref": "#/components/parameters/CorrelationId"}]
        operation["responses"]["200"]["headers"] = _response_headers()

    document["paths"]["/health"]["get"]["security"] = []
    ready_operation = document["paths"]["/ready"]["get"]
    ready_operation["responses"]["503"]["description"] = "Surface is not ready"
    ready_operation["responses"]["503"]["headers"] = _response_headers(
        include_retry_after=True
    )
    ready_operation["responses"]["200"]["description"] = "Surface is ready or degraded"
    version_operation = document["paths"]["/version"]["get"]
    version_operation["responses"]["200"]["description"] = (
        "Immutable version identity for this surface"
    )

    for operation in (ready_operation, version_operation):
        operation["responses"]["401"] = {"$ref": "#/components/responses/Unauthorized"}
        operation["responses"]["403"] = {"$ref": "#/components/responses/Forbidden"}

    # Product operations use the same correlation contract as runtime probes;
    # BFF credentials and forwarding metadata remain intentionally undocumented.
    for path, path_item in document["paths"].items():
        if path in path_metadata:
            continue
        for operation in path_item.values():
            if isinstance(operation, dict) and "operationId" in operation:
                operation["parameters"] = [{"$ref": "#/components/parameters/CorrelationId"}]

    health_response = document["paths"]["/health"]["get"]["responses"]["200"]
    health_response["description"] = "Process is alive"
    health_response["content"]["application/json"]["examples"] = {
        "alive": {"value": {"status": "alive"}}
    }


def _openapi_for_app(app: FastAPI) -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema
    document = get_openapi(
        title="Umbral Runtime API",
        version="1.0.0",
        description=_RUNTIME_DESCRIPTION,
        routes=app.routes,
    )
    _apply_runtime_openapi_contract(document)
    app.openapi_schema = document
    return document


def create_app() -> FastAPI:
    """Compose the API with validated configuration and safe transport policy."""

    dependencies = build_runtime_dependencies()

    def observe_api_surface() -> None:
        writer = dependencies.heartbeat_writer
        if writer is None:
            return
        try:
            report = dependencies.readiness.evaluate()
            writer.observe(
                "api",
                state=report.state,
                checks={check.name: check.state for check in report.checks},
            )
        except Exception:
            pass

    async def api_heartbeat_loop() -> None:
        while True:
            await asyncio.to_thread(observe_api_surface)
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)

    @asynccontextmanager
    async def observability_lifespan(_: FastAPI) -> AsyncIterator[None]:
        initialize_observability(dependencies.settings)
        heartbeat_task: asyncio.Task[None] | None = None
        if dependencies.heartbeat_writer is not None:
            heartbeat_task = asyncio.create_task(api_heartbeat_loop())
        try:
            yield
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task
            shutdown_observability()

    app = FastAPI(
        title="Umbral Runtime API",
        version="1.0.0",
        lifespan=observability_lifespan,
    )
    configure_runtime_routes(dependencies)
    configure_auth_routes(dependencies)
    app.add_middleware(CorrelationMiddleware)
    app.add_exception_handler(ApplicationError, application_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(runtime_router)
    app.include_router(auth_router)
    app.include_router(email_webhook_router)

    def custom_openapi() -> dict[str, Any]:
        return _openapi_for_app(app)

    setattr(app, "openapi", custom_openapi)
    return app


app = create_app()
