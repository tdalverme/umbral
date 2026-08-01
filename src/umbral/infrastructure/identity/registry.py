"""Environment-scoped provider registry."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from umbral.application.identity.ports import EmailPort, IdentityProofPort
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.email.resend import ResendEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider
from umbral.infrastructure.identity.supabase import (
    SupabaseIdentityAdapter,
    build_supabase_client,
)


@dataclass(frozen=True, slots=True)
class EnvironmentIdentityPolicy:
    environment: str
    issuer: str
    capture_origin: str
    email_provider: str

    def assert_capture_url(self, capture_url: str) -> None:
        parsed = urlparse(capture_url)
        expected = urlparse(self.capture_origin)
        if (
            parsed.scheme,
            parsed.hostname,
            parsed.port,
        ) != (
            expected.scheme,
            expected.hostname,
            expected.port,
        ) or parsed.path != "/auth/capture":
            raise ValueError("capture URL is outside the environment allowlist")


@dataclass(frozen=True, slots=True)
class IdentityProviderRegistry:
    identity: IdentityProofPort
    email: EmailPort
    enabled: bool
    policy: EnvironmentIdentityPolicy


def build_identity_registry(settings: Settings) -> IdentityProviderRegistry:
    if settings.identity_provider == "supabase":
        if not settings.supabase_url or not settings.supabase_secret_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
        identity: IdentityProofPort = SupabaseIdentityAdapter(
            issuer=settings.identity_issuer,
            capture_origin=settings.identity_capture_origin,
            client=build_supabase_client(
                url=settings.supabase_url,
                secret_key=settings.supabase_secret_key,
            ),
        )
    elif settings.identity_provider == "fake" and settings.environment == "local":
        identity = FakeIdentityProvider(
            issuer=settings.identity_issuer,
            capture_origin=settings.identity_capture_origin,
        )
    else:
        raise ValueError("identity provider is unavailable outside local development")
    email: EmailPort = RecordingEmailAdapter()
    if settings.email_provider == "resend" and settings.resend_api_key:
        email = ResendEmailAdapter(
            api_key=settings.resend_api_key,
            webhook_secret=(
                settings.email_webhook_secret or settings.resend_api_key
            ).encode(),
        )
    return IdentityProviderRegistry(
        identity=identity,
        email=email,
        enabled=True,
        policy=EnvironmentIdentityPolicy(
            environment=settings.environment,
            issuer=settings.identity_issuer,
            capture_origin=settings.identity_capture_origin.rstrip("/"),
            email_provider=email.provider,
        ),
    )
