"""Dev-only HTTP surface for the local playground."""

from __future__ import annotations

from typing import Literal, cast

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, model_validator

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.playground.contracts import (
    ConversationRequest,
    GeoInspectionRequest,
)
from umbral.infrastructure.playground.fixtures import (
    PlaygroundFixtures,
    load_playground_catalog,
)
from umbral.infrastructure.playground.trace import primitive

router = APIRouter(prefix="/api/v1/playground", tags=["Playground"])
_dependencies: RuntimeDependencies | None = None
_catalog: PlaygroundFixtures | None = None


class ConversationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str = Field(min_length=1)
    turns: list[str] = Field(min_length=1, max_length=20)
    model_mode: Literal["fake", "real"] = "fake"


class GeoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str = Field(min_length=1)
    listing_id: str | None = Field(default=None, min_length=1)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_m: int = Field(default=600, ge=50, le=5000)

    @model_validator(mode="after")
    def validate_target(self) -> "GeoBody":
        has_listing = self.listing_id is not None
        has_point = self.latitude is not None or self.longitude is not None
        if has_listing == has_point:
            raise ValueError("send either listing_id or latitude and longitude")
        if has_point and (self.latitude is None or self.longitude is None):
            raise ValueError("latitude and longitude are required together")
        return self


def configure_playground_routes(
    dependencies: RuntimeDependencies, *, catalog: PlaygroundFixtures | None = None
) -> None:
    global _catalog, _dependencies
    _dependencies = dependencies
    _catalog = catalog


def _deps() -> RuntimeDependencies:
    if _dependencies is None or _dependencies.playground is None:
        raise RuntimeError("playground routes were not configured")
    return _dependencies


@router.get("/fixtures")
def list_fixtures() -> dict[str, object]:
    fixtures = _catalog or load_playground_catalog()
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
    playground = _deps().playground
    if playground is None:
        raise RuntimeError("playground routes were not configured")
    result = playground.run_conversation(
        ConversationRequest(
            fixture_id=body.fixture_id,
            turns=tuple(body.turns),
            model_mode=body.model_mode,
        )
    )
    return cast(dict[str, object], primitive(result))


@router.post("/geo")
def inspect_geo(body: GeoBody) -> dict[str, object]:
    playground = _deps().playground
    if playground is None:
        raise RuntimeError("playground routes were not configured")
    result = playground.inspect_listing_geo(
        GeoInspectionRequest(
            fixture_id=body.fixture_id,
            listing_id=body.listing_id,
            radius_m=body.radius_m,
            latitude=body.latitude,
            longitude=body.longitude,
        )
    )
    return cast(dict[str, object], primitive(result))
