"""Operator authorization for the import entry using the real policy matrix."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.support.identity import access_with_recording_jobs, requested_attempt
from umbral.api.dependencies import RuntimeDependencies
from umbral.api.routers.imports import configure_imports_routes, router
from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.administration import AccessAdministration
from umbral.application.identity.authorization import AccessControl
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures" / "imports"
COOKIE = "umbral_test_session"


def _login(store: InMemoryIdentityStore) -> str:
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    AccessAdministration(store).preload_invitation("person@example.com")
    email = RecordingEmailAdapter()
    access = access_with_recording_jobs(store, FakeIdentityProvider(), email)
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="o",
        correlation_id=uuid4(),
        now=now,
    )
    attempt = requested_attempt(access, store)
    access.issue_attempt(attempt.id, now=now)
    token_hash = str(email.messages[0]["capture_url"]).split("token_hash=", 1)[1]
    return access.confirm_magic_link(
        attempt_id=attempt.id, token_hash=str(token_hash), now=now
    ).token


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


def _client(
    store: InMemoryIdentityStore, access: IdentityAccess | None = None
) -> TestClient:
    from tests.fakes.imports import make_import_service
    from umbral.infrastructure.ingestion.contract_loader import load_contract_v1

    service, _ = make_import_service(contract=load_contract_v1())
    deps = RuntimeDependencies(
        settings=_settings(),
        release=None,  # type: ignore[arg-type]
        readiness=None,  # type: ignore[arg-type]
        object_store=None,  # type: ignore[arg-type]
        identity_store=store,
        identity_access=access,  # type: ignore[arg-type]
        access_control=AccessControl(store),
        administration=None,  # type: ignore[arg-type]
        ingestion=service,
    )
    app = FastAPI()
    configure_imports_routes(deps)
    app.include_router(router)
    return TestClient(app)


def _payload() -> dict[str, Any]:
    raw = (FIXTURES / "reference-batch.json").read_bytes()
    return {
        "files": {"file": ("reference-batch.json", raw, "application/json")},
        "data": {
            "source_id": "source-a",
            "source_version": "v1",
            "contract_version": "1",
        },
    }


def test_operator_role_can_submit_and_read_runs() -> None:
    store = InMemoryIdentityStore()
    token = _login(store)
    user = store.user_for_email("person@example.com")
    assert user is not None
    AccessAdministration(store).change_role(user.id, "operator", grant=True)

    client = _client(store)
    submitted = client.post(
        "/api/v1/imports/batches", cookies={COOKIE: token}, **_payload()
    )
    assert submitted.status_code == 202
    run_id = submitted.json()["run_id"]
    read = client.get(f"/api/v1/imports/runs/{run_id}", cookies={COOKIE: token})
    assert read.status_code == 200
    assert read.json()["run_id"] == run_id


def test_user_role_is_denied() -> None:
    store = InMemoryIdentityStore()
    token = _login(store)
    client = _client(store)
    response = client.post(
        "/api/v1/imports/batches", cookies={COOKIE: token}, **_payload()
    )
    assert response.status_code == 403
    assert response.json()["code"] == "auth.access_denied"


def test_missing_session_is_401() -> None:
    store = InMemoryIdentityStore()
    client = _client(store)
    response = client.post("/api/v1/imports/batches", **_payload())
    assert response.status_code == 401
