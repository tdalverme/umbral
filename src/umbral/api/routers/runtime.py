"""Side-effect-free public runtime probe endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from umbral.api.dependencies import RuntimeDependencies
from umbral.application.runtime.readiness import DependencyCheckName
from umbral.domain.errors import InvalidRequestError

router = APIRouter(tags=["Runtime"])
_runtime_dependencies: RuntimeDependencies | None = None


class HealthResponse(BaseModel):
    """Minimal liveness contract."""

    model_config = ConfigDict(extra="forbid")
    status: Literal["alive"]


class DependencyCheckResponse(BaseModel):
    """One allowlisted readiness check."""

    model_config = ConfigDict(extra="forbid")
    name: DependencyCheckName
    state: Literal["ready", "degraded", "unavailable"]
    critical: bool
    code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.-]{0,99}$")


class ReadinessResponse(BaseModel):
    """Readiness response contract."""

    model_config = ConfigDict(extra="forbid")
    surface: Literal["web", "api", "worker", "scheduler"]
    state: Literal["ready", "degraded", "not_ready"]
    observed_at: datetime
    release_id: str = Field(min_length=1, max_length=100)
    checks: list[DependencyCheckResponse] = Field(max_length=12)


class RuntimeVersionResponse(BaseModel):
    """Immutable executing release identity."""

    model_config = ConfigDict(extra="forbid")
    surface: Literal["web", "api", "worker", "scheduler"]
    release_id: str = Field(min_length=1, max_length=100)
    git_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    artifact_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_major: Literal[1]
    database_revision: str = Field(min_length=1, max_length=64)
    built_at: datetime


def configure_runtime_routes(dependencies: RuntimeDependencies) -> None:
    """Bind immutable dependencies once in the composition root."""

    global _runtime_dependencies
    _runtime_dependencies = dependencies


def _dependencies() -> RuntimeDependencies:
    if _runtime_dependencies is None:
        raise RuntimeError("runtime routes were not configured")
    return _runtime_dependencies


def _assert_no_query_parameters(request: Request) -> None:
    if request.query_params:
        raise InvalidRequestError()


@router.get("/health", operation_id="getRuntimeHealth", response_model=HealthResponse)
async def health(request: Request, response: Response) -> HealthResponse:
    """Confirm only that this process can respond."""

    _assert_no_query_parameters(request)
    response.headers["Cache-Control"] = "no-store"
    return HealthResponse(status="alive")


@router.get(
    "/ready",
    operation_id="getRuntimeReadiness",
    response_model=ReadinessResponse,
    response_model_exclude_none=True,
    responses={503: {"model": ReadinessResponse}},
)
async def ready(request: Request, response: Response) -> ReadinessResponse:
    """Report this API surface's already-known readiness."""

    _assert_no_query_parameters(request)
    report = _dependencies().readiness.evaluate()
    response.headers["Cache-Control"] = "no-store"
    if report.state == "not_ready":
        response.status_code = 503
        response.headers["Retry-After"] = "30"
    return ReadinessResponse(
        surface=report.surface,
        state=report.state,
        observed_at=report.observed_at,
        release_id=report.release_id,
        checks=[
            DependencyCheckResponse(
                name=check.name,
                state=check.state,
                critical=check.critical,
                code=check.code,
            )
            for check in report.checks
        ],
    )


@router.get(
    "/version",
    operation_id="getRuntimeVersion",
    response_model=RuntimeVersionResponse,
)
async def version(request: Request, response: Response) -> RuntimeVersionResponse:
    """Identify the immutable release backing the API surface."""

    _assert_no_query_parameters(request)
    response.headers["Cache-Control"] = "no-store"
    release = _dependencies().release
    return RuntimeVersionResponse(
        surface="api",
        release_id=release.release_id,
        git_sha=release.git_sha,
        artifact_digest=release.artifacts["runtime"].digest,
        manifest_sha256=release.manifest_sha256,
        contract_major=1,
        database_revision=release.database_revision,
        built_at=datetime.fromisoformat(release.built_at.replace("Z", "+00:00")),
    )
