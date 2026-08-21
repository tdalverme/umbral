"""Operator entry API: submit, run read, quality and authorization wiring."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.fakes.imports import make_import_service

from umbral.api.dependencies import RuntimeDependencies
from umbral.api.routers.imports import configure_imports_routes, router
from umbral.application.identity.authorization import AccessControl
from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.infrastructure.config.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures" / "imports"
COOKIE = "umbral_local_session"


_OPS_ACTIONS = frozenset(
    {
        "ops.ingestion.batch.submit",
        "ops.ingestion.run.read",
        "ops.ingestion.quality.read",
    }
)


class FakeAccessControl:
    def __init__(
        self, principal: CurrentPrincipal | None, error: IdentityError | None
    ) -> None:
        self.principal = principal
        self.error = error

    def authorize(
        self,
        token: str,
        *,
        action: str,
        resource_owner_id: object,
        now: datetime,
        correlation_id: object = None,
    ) -> CurrentPrincipal:
        del token, resource_owner_id, now, correlation_id
        if self.error is not None:
            raise self.error
        if self.principal is None:
            raise IdentityError("auth.session_required", status=401, recovery="sign_in")
        if action in _OPS_ACTIONS and not set(self.principal.roles) & {
            "operator",
            "administrator",
        }:
            raise IdentityError(
                "auth.access_denied", status=403, recovery="contact_support"
            )
        return self.principal


def _settings() -> Settings:
    return Settings.from_environment(
        {
            "UMBRAL_ENV": "local",
            "UMBRAL_RELEASE_ID": "foundation-local",
            "UMBRAL_RELEASE_MANIFEST": "<local>",
            "DATABASE_URL": "postgresql://umbral:local@127.0.0.1/umbral",
            "REDIS_URL": "redis://127.0.0.1:6379/0",
            "OBJECT_STORE_BACKEND": "filesystem",
            "OBJECT_STORE_ROOT": ".umbral-local",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
            "UMBRAL_API_BASE_URL": "http://127.0.0.1:8000",
            "SESSION_COOKIE_NAME": COOKIE,
            "SESSION_SECURE": "false",
        }
    )


def _app(
    principal: CurrentPrincipal | None = None,
    error: IdentityError | None = None,
) -> TestClient:
    from umbral.infrastructure.ingestion.contract_loader import load_contract_v2

    service, _ = make_import_service(contract=load_contract_v2())
    deps = RuntimeDependencies(
        settings=_settings(),
        release=None,  # type: ignore[arg-type]
        readiness=None,  # type: ignore[arg-type]
        object_store=None,  # type: ignore[arg-type]
        identity_store=None,  # type: ignore[arg-type]
        identity_access=None,  # type: ignore[arg-type]
        access_control=cast(AccessControl, FakeAccessControl(principal, error)),
        administration=None,  # type: ignore[arg-type]
        ingestion=service,
    )
    app = FastAPI()
    configure_imports_routes(deps)
    app.include_router(router)
    return TestClient(app)


OPERATOR = CurrentPrincipal(
    uuid4(), ("operator",), datetime(2026, 8, 1, tzinfo=timezone.utc)
)


def _batch_payload() -> dict[str, Any]:
    raw = (FIXTURES / "reference-batch.json").read_bytes()
    return {
        "files": {"file": ("reference-batch.json", raw, "application/json")},
        "data": {
            "source_id": "source-a",
            "source_version": "v1",
            "contract_version": "2",
        },
    }


def test_operator_can_submit_a_batch() -> None:
    client = _app(principal=OPERATOR)
    response = client.post(
        "/api/v1/imports/batches", cookies={COOKIE: "token"}, **_batch_payload()
    )
    assert response.status_code == 202
    body = response.json()
    assert body["state"] == "pending"
    assert body["total_records"] == 0


def test_anonymous_submit_is_rejected() -> None:
    client = _app(principal=None)
    response = client.post("/api/v1/imports/batches", **_batch_payload())
    assert response.status_code == 401
    assert response.json()["code"] == "auth.session_required"


def test_non_operator_submit_is_rejected() -> None:
    user = CurrentPrincipal(
        uuid4(), ("user",), datetime(2026, 8, 1, tzinfo=timezone.utc)
    )
    client = _app(principal=user)
    response = client.post(
        "/api/v1/imports/batches", cookies={COOKIE: "token"}, **_batch_payload()
    )
    assert response.status_code == 403


def test_batch_with_invalid_contract_version_is_rejected_with_code() -> None:
    client = _app(principal=OPERATOR)
    payload = _batch_payload()
    payload["data"]["contract_version"] = "9"
    response = client.post(
        "/api/v1/imports/batches", cookies={COOKIE: "token"}, **payload
    )
    assert response.status_code == 400
    assert response.json()["code"] in {"request.invalid"}


def test_url_is_not_accepted_instead_of_a_file() -> None:
    client = _app(principal=OPERATOR)
    response = client.post(
        "/api/v1/imports/batches",
        cookies={COOKIE: "token"},
        data={
            "source_id": "source-a",
            "source_version": "v1",
            "contract_version": "2",
        },
    )
    assert response.status_code in {400, 422}


def test_run_read_requires_operator_role() -> None:
    client = _app(
        principal=OPERATOR,
        error=IdentityError(
            "auth.access_denied", status=403, recovery="contact_support"
        ),
    )
    response = client.get(f"/api/v1/imports/runs/{uuid4()}", cookies={COOKIE: "token"})
    assert response.status_code == 403


def test_repeat_submit_returns_the_same_run() -> None:
    client = _app(principal=OPERATOR)
    first = client.post(
        "/api/v1/imports/batches", cookies={COOKIE: "token"}, **_batch_payload()
    ).json()
    second = client.post(
        "/api/v1/imports/batches", cookies={COOKIE: "token"}, **_batch_payload()
    ).json()
    assert first["run_id"] == second["run_id"]


def test_derived_batch_key_is_file_hash() -> None:
    raw = (FIXTURES / "reference-batch.json").read_bytes()
    client = _app(principal=OPERATOR)
    body = client.post(
        "/api/v1/imports/batches", cookies={COOKIE: "token"}, **_batch_payload()
    ).json()
    assert body["batch_key"] == hashlib.sha256(raw).hexdigest()
