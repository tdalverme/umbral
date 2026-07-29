from __future__ import annotations

# ruff: noqa: E501
from datetime import datetime, timezone
from uuid import uuid4

from umbral.infrastructure.identity.fake import FakeIdentityProvider


def test_fake_provider_uses_explicit_redirect_and_short_expiry() -> None:
    provider = FakeIdentityProvider(capture_origin="http://localhost:3000")
    link = provider.generate_magic_link(attempt_id=uuid4(), email="p@example.com", now=datetime.now(timezone.utc))
    assert link.capture_url.startswith("http://localhost:3000/auth/capture?")
    assert (link.expires_at - link.generated_at).total_seconds() == 900
