"""Minimal local API entrypoint for the no-database development playground."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from fastapi import FastAPI

from umbral.api.dependencies import RuntimeDependencies
from umbral.api.routers.playground import (
    configure_playground_routes,
)
from umbral.api.routers.playground import (
    router as playground_router,
)
from umbral.application.playground.service import PlaygroundService
from umbral.infrastructure.playground.conversation import (
    build_local_conversation_runner,
)
from umbral.infrastructure.playground.geo import build_local_geo_inspector


def create_playground_app() -> FastAPI:
    service = PlaygroundService(
        conversation=build_local_conversation_runner(),
        geo=build_local_geo_inspector(),
    )
    dependencies = cast(
        RuntimeDependencies,
        SimpleNamespace(playground=service),
    )
    configure_playground_routes(dependencies)
    app = FastAPI(title="Umbral Local Playground", version="local")
    app.include_router(playground_router)
    return app


app = create_playground_app()

