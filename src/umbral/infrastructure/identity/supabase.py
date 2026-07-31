"""Supabase adapter boundary with lazy SDK integration.

The application only sees ``IdentityProofPort`` values.  A deployment may
provide a callable client; no Supabase object is exposed to application code.
"""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from uuid import UUID

from umbral.application.identity.contracts import (
    GeneratedMagicLink,
    IdentityError,
    ProviderProof,
)


class SupabaseIdentityAdapter:
    provider = "supabase"

    def __init__(self, *, issuer: str, capture_origin: str, generate: Callable[..., Mapping[str, object]] | None = None, verify: Callable[..., Mapping[str, object]] | None = None) -> None:
        self.issuer = issuer
        self.capture_origin = capture_origin.rstrip("/")
        self._generate = generate
        self._verify = verify

    def generate_magic_link(self, *, attempt_id: UUID, email: str, now: datetime) -> GeneratedMagicLink:
        if self._generate is None:
            raise IdentityError("auth.provider_unavailable", status=503, recovery="retry_later")
        try:
            result = self._generate(email=email, redirect_to=f"{self.capture_origin}/auth/capture", attempt_id=attempt_id)
            token_hash = str(result["token_hash"])
            expires_at = result.get("expires_at", now)
            return GeneratedMagicLink("supabase", attempt_id, token_hash, f"{self.capture_origin}/auth/capture?attempt_id={attempt_id}&token_hash={token_hash}", now, expires_at if isinstance(expires_at, datetime) else now)
        except Exception as exc:
            raise IdentityError("auth.provider_unavailable", status=503, recovery="retry_later") from exc

    def verify_magic_link(self, *, attempt_id: UUID, token_hash: str, now: datetime) -> ProviderProof:
        if self._verify is None:
            raise IdentityError("auth.provider_unavailable", status=503, recovery="retry_later")
        try:
            result = self._verify(token_hash=token_hash)
            issuer = str(result.get("issuer", ""))
            subject = str(result.get("subject", ""))
            email = str(result.get("verified_email", ""))
            if issuer != self.issuer or not subject or not email:
                raise IdentityError("auth.link_unavailable", status=410, recovery="request_new_link")
            return ProviderProof("supabase", issuer, subject, email, now)
        except IdentityError:
            raise
        except Exception as exc:
            raise IdentityError("auth.provider_unavailable", status=503, recovery="retry_later") from exc

    def revoke_provider_session(self, handle: str) -> None:
        return None

    def health(self) -> str:
        return "ready" if self._generate is not None and self._verify is not None else "unavailable"
