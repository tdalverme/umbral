from __future__ import annotations

# ruff: noqa: E501
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from umbral.infrastructure.identity.fake import FakeIdentityProvider
from umbral.infrastructure.identity.registry import build_identity_registry
from umbral.infrastructure.identity.supabase import SupabaseIdentityAdapter


def test_fake_provider_uses_explicit_redirect_and_short_expiry() -> None:
    provider = FakeIdentityProvider(capture_origin="http://localhost:3000")
    link = provider.generate_magic_link(
        attempt_id=uuid4(), email="p@example.com", now=datetime.now(timezone.utc)
    )
    assert link.capture_url.startswith("http://localhost:3000/auth/capture?")
    assert (link.expires_at - link.generated_at).total_seconds() == 900


def test_supabase_registry_composes_the_sdk_client_without_exposing_its_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}
    sdk_client = object()

    def build_client(*, url: str, secret_key: str) -> object:
        captured.update(url=url, secret_key=secret_key)
        return sdk_client

    monkeypatch.setattr(
        "umbral.infrastructure.identity.registry.build_supabase_client", build_client
    )
    settings = SimpleNamespace(
        environment="preview",
        identity_provider="supabase",
        supabase_url="https://project.supabase.co",
        supabase_secret_key="sb_secret_test_value",
        identity_issuer="https://project.supabase.co/auth/v1",
        identity_capture_origin="https://preview.umbral.invalid",
        email_provider="recording",
        resend_api_key=None,
        email_webhook_secret=None,
    )

    registry = build_identity_registry(settings)  # type: ignore[arg-type]

    assert captured == {
        "url": "https://project.supabase.co",
        "secret_key": "sb_secret_test_value",
    }
    assert isinstance(registry.identity, SupabaseIdentityAdapter)
    assert registry.identity.health() == "ready"


@pytest.mark.parametrize("field", ["supabase_url", "supabase_secret_key"])
def test_supabase_registry_rejects_missing_required_configuration(field: str) -> None:
    settings = SimpleNamespace(
        environment="preview",
        identity_provider="supabase",
        supabase_url="https://project.supabase.co",
        supabase_secret_key="sb_secret_test_value",
        identity_issuer="https://project.supabase.co/auth/v1",
        identity_capture_origin="https://preview.umbral.invalid",
        email_provider="recording",
        resend_api_key=None,
        email_webhook_secret=None,
    )
    setattr(settings, field, None)

    with pytest.raises(ValueError):
        build_identity_registry(settings)  # type: ignore[arg-type]
