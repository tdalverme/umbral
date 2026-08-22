"""Dev-only HTTP surface for the local playground."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.playground.contracts import (
    ConversationRequest,
    GeoInspectionRequest,
)
from umbral.infrastructure.playground.fixtures import load_fixtures
from umbral.infrastructure.playground.trace import primitive

router = APIRouter(prefix="/api/v1/playground", tags=["Playground"])
_dependencies: RuntimeDependencies | None = None


class ConversationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str = Field(min_length=1)
    turns: list[str] = Field(min_length=1, max_length=20)
    model_mode: Literal["fake", "real"] = "fake"


class GeoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str = Field(min_length=1)
    listing_id: str = Field(min_length=1)
    radius_m: int = Field(default=600, ge=50, le=5000)


def configure_playground_routes(dependencies: RuntimeDependencies) -> None:
    global _dependencies
    _dependencies = dependencies


def _deps() -> RuntimeDependencies:
    if _dependencies is None or _dependencies.playground is None:
        raise RuntimeError("playground routes were not configured")
    return _dependencies


@router.get("/fixtures")
def list_fixtures() -> dict[str, object]:
    fixtures = load_fixtures()
    return {
        "fixtures": [
            {
                "id": item.fixture_id,
                "profile": primitive(item.profile),
                "listings": primitive(item.listings),
            }
            for item in fixtures.items
        ]
    }


@router.post("/conversations")
def run_conversation(body: ConversationBody) -> dict[str, object]:
    result = _deps().playground.run_conversation(
        ConversationRequest(
            fixture_id=body.fixture_id,
            turns=tuple(body.turns),
            model_mode=body.model_mode,
        )
    )
    return primitive(result)


@router.post("/geo")
def inspect_geo(body: GeoBody) -> dict[str, object]:
    result = _deps().playground.inspect_listing_geo(
        GeoInspectionRequest(
            fixture_id=body.fixture_id,
            listing_id=body.listing_id,
            radius_m=body.radius_m,
        )
    )
    return primitive(result)

