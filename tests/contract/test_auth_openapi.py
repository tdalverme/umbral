from __future__ import annotations

from umbral.api.main import app


def test_auth_openapi_has_bff_boundary_and_no_public_signup() -> None:
    document = app.openapi()
    paths = document["paths"]
    assert "/api/v1/auth/magic-link-requests" in paths
    assert "/api/v1/auth/magic-link-confirmations" in paths
    assert "/api/v1/auth/signup" not in paths
    assert "X-Umbral-BFF-Token" not in str(paths["/api/v1/auth/magic-link-requests"])
