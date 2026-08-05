"""Environment-scoped provider registry."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlparse

import resend

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
    if settings.email_provider == "resend":
        if (
            not settings.resend_api_key
            or not settings.resend_from_email
            or not settings.email_webhook_secret
        ):
            raise ValueError(
                "Resend API key, sender email, and webhook secret are required"
            )
        resend.api_key = settings.resend_api_key
        email = ResendEmailAdapter(
            sender_email=settings.resend_from_email,
            webhook_secret=settings.email_webhook_secret,
            sender=_resend_sender(settings.resend_api_key),
            verifier=lambda options: cast(Any, resend.Webhooks.verify)(options),
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


def _resend_sender(
    api_key: str,
) -> Callable[[Mapping[str, object], Mapping[str, str]], Mapping[str, object]]:
    """Send through the Resend API with a client signature Cloudflare accepts.

    The resend SDK identifies itself as ``resend-python``, which the provider
    rejects with an HTTP 1010 browser check; a plain JSON POST with a curl
    user agent matches the reachability probe and reliably delivers.
    """

    def send(
        params: Mapping[str, object], options: Mapping[str, str]
    ) -> Mapping[str, object]:
        del options
        import json as json_module
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen

        body = json_module.dumps(dict(params), separators=(",", ":")).encode()
        request = Request(
            "https://api.resend.com/emails",
            method="POST",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "curl/8.7.1",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310
                payload = json_module.loads(response.read())
        except HTTPError as error:
            error.read()
            raise
        if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
            raise ValueError("resend send response is invalid")
        return payload

    return send
