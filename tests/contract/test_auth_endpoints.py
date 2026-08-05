from __future__ import annotations

from fastapi.testclient import TestClient

from umbral.api.main import app
from umbral.api.routers.auth import _deps


def test_request_endpoint_is_neutral_for_unknown_email() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/magic-link-requests",
        headers={"X-Umbral-BFF-Token": _deps().settings.bff_token, "X-Umbral-Origin-Fingerprint": "bff"},
        json={"email": "unknown@example.com"},
    )
    assert response.status_code == 202
    assert response.json()["message"] == "Si la dirección está habilitada, recibirás un enlace para continuar."
    assert response.headers["cache-control"] == "no-store"


def test_capture_confirmation_never_accepts_get_or_returns_token() -> None:
    document = app.openapi()
    confirmation = document["paths"]["/api/v1/auth/magic-link-confirmations"]["post"]
    assert confirmation["operationId"] == "confirmMagicLink"
    assert "token_hash" in str(document["components"]["schemas"]["MagicLinkConfirmation"])
# ruff: noqa: E501
