"""Side-effect-free public runtime probe endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from umbral.api.dependencies import RuntimeDependencies
from umbral.api.routers.auth import _check_bff
from umbral.application.runtime.readiness import DependencyCheckName
from umbral.domain.errors import InvalidRequestError

router = APIRouter(tags=["Runtime"])
_runtime_dependencies: RuntimeDependencies | None = None


class Health(BaseModel):
    """Minimal liveness contract."""

    model_config = ConfigDict(extra="forbid")
    status: Literal["alive"]


class DependencyCheck(BaseModel):
    """One allowlisted readiness check."""

    model_config = ConfigDict(extra="forbid")
    name: DependencyCheckName
    state: Literal["ready", "degraded", "unavailable"]
    critical: bool
    code: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.-]{0,99}$")


class Readiness(BaseModel):
    """Readiness response contract."""

    model_config = ConfigDict(extra="forbid")
    surface: Literal["web", "api", "worker", "scheduler"]
    state: Literal["ready", "degraded", "not_ready"]
    observed_at: datetime
    release_id: str = Field(min_length=1, max_length=100)
    checks: list[DependencyCheck] = Field(max_length=12)


class RuntimeVersion(BaseModel):
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


class ValidationIssue(BaseModel):
    """Safe field-level validation metadata for RFC 9457 problems."""

    model_config = ConfigDict(extra="forbid")
    field: str
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")


class Problem(BaseModel):
    """Sanitized RFC 9457 problem details contract."""

    model_config = ConfigDict(extra="forbid")
    type: str = Field(json_schema_extra={"format": "uri"})
    title: str = Field(max_length=200)
    status: int = Field(ge=400, le=599)
    detail: str | None = Field(default=None, max_length=500)
    instance: str | None = None
    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    request_id: UUID
    correlation_id: UUID
    errors: list[ValidationIssue] | None = Field(default=None, max_length=50)


class InternalWebHeartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["ready", "degraded", "not_ready"]
    checks: dict[str, str]


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


@router.get("/health", operation_id="getRuntimeHealth", response_model=Health)
async def health(request: Request, response: Response) -> Health:
    """Confirm only that this process can respond."""

    _assert_no_query_parameters(request)
    response.headers["Cache-Control"] = "no-store"
    return Health(status="alive")


@router.get(
    "/ready",
    operation_id="getRuntimeReadiness",
    response_model=Readiness,
    response_model_exclude_none=True,
    responses={
        401: {
            "model": Problem,
            "description": "Missing or invalid environment identity",
        },
        403: {
            "model": Problem,
            "description": (
                "Valid environment identity without access to this environment"
            ),
        },
        503: {"model": Readiness},
    },
)
async def ready(request: Request, response: Response) -> Readiness:
    """Report this API surface's already-known readiness."""

    _assert_no_query_parameters(request)
    report = _dependencies().readiness.evaluate()
    writer = _dependencies().heartbeat_writer
    if writer is not None:
        writer.observe(
            "api",
            state=report.state,
            checks={check.name: check.state for check in report.checks},
        )
    response.headers["Cache-Control"] = "no-store"
    if report.state == "not_ready":
        response.status_code = 503
        response.headers["Retry-After"] = "30"
    return Readiness(
        surface=report.surface,
        state=report.state,
        observed_at=report.observed_at,
        release_id=report.release_id,
        checks=[
            DependencyCheck(
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
    response_model=RuntimeVersion,
    responses={
        401: {
            "model": Problem,
            "description": "Missing or invalid environment identity",
        },
        403: {
            "model": Problem,
            "description": (
                "Valid environment identity without access to this environment"
            ),
        },
    },
)
async def version(request: Request, response: Response) -> RuntimeVersion:
    """Identify the immutable release backing the API surface."""

    _assert_no_query_parameters(request)
    response.headers["Cache-Control"] = "no-store"
    release = _dependencies().release
    return RuntimeVersion(
        surface="api",
        release_id=release.release_id,
        git_sha=release.git_sha,
        artifact_digest=release.artifacts["runtime"].digest,
        manifest_sha256=release.manifest_sha256,
        contract_major=1,
        database_revision=release.database_revision,
        built_at=datetime.fromisoformat(release.built_at.replace("Z", "+00:00")),
    )


@router.post(
    "/internal/runtime/web-heartbeat", include_in_schema=False, status_code=204
)
async def web_heartbeat(
    payload: InternalWebHeartbeat,
    x_umbral_bff_token: str | None = Header(default=None, include_in_schema=False),
) -> Response:
    """Accept the web's private heartbeat only through the BFF credential."""

    _check_bff(x_umbral_bff_token)
    writer = _dependencies().heartbeat_writer
    if writer is None:
        return Response(status_code=204)
    writer.observe("web", state=payload.state, checks=payload.checks)
    return Response(status_code=204)
