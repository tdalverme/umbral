"""Minimal local API entrypoint for the no-database development playground."""

from __future__ import annotations

import os
from pathlib import Path
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
from umbral.infrastructure.playground.fixtures import load_playground_catalog
from umbral.infrastructure.playground.geo import LocalGeoInspector


def create_playground_app() -> FastAPI:
    snapshot_value = os.environ.get("PLAYGROUND_SNAPSHOT_PATH", "").strip()
    snapshot_path = Path(snapshot_value) if snapshot_value else None
    catalog = load_playground_catalog(snapshot_path)
    service = PlaygroundService(
        conversation=build_local_conversation_runner(),
        geo=LocalGeoInspector(catalog),
    )
    dependencies = cast(
        RuntimeDependencies,
        SimpleNamespace(playground=service),
    )
    configure_playground_routes(dependencies, catalog=catalog)
    app = FastAPI(title="Umbral Local Playground", version="local")
    app.include_router(playground_router)
    return app


app = create_playground_app()
