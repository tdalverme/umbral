"""API composition root for the foundation runtime."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from umbral.api.dependencies import build_runtime_dependencies
from umbral.api.errors import (
    application_error_handler,
    http_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from umbral.api.middleware.correlation import CorrelationMiddleware
from umbral.api.routers.runtime import configure_runtime_routes
from umbral.api.routers.runtime import router as runtime_router
from umbral.domain.errors import ApplicationError


def create_app() -> FastAPI:
    """Compose the API with validated configuration and safe transport policy."""

    app = FastAPI(title="Umbral Runtime API", version="1.0.0")
    configure_runtime_routes(build_runtime_dependencies())
    app.add_middleware(CorrelationMiddleware)
    app.add_exception_handler(ApplicationError, application_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
    app.include_router(runtime_router)
    return app


app = create_app()
