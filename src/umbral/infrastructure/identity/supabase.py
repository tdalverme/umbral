"""Supabase adapter boundary with lazy SDK integration.

The application only sees ``IdentityProofPort`` values.  A deployment may
provide a callable client; no Supabase object is exposed to application code.
"""
# ruff: noqa: E501

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.parse import urlencode
from uuid import UUID

from supabase import Client, create_client

from umbral.application.identity.contracts import (
    GeneratedMagicLink,
    IdentityError,
    ProviderProof,
)
from umbral.domain.identity.email import normalize_email


def build_supabase_client(*, url: str, secret_key: str) -> Client:
    """Create the server-only SDK client at the infrastructure boundary."""

    return create_client(url, secret_key)


class _SupabaseClient(Protocol):
    auth: Any


class SupabaseIdentityAdapter:
    provider = "supabase"

    def __init__(
        self, *, issuer: str, capture_origin: str, client: _SupabaseClient
    ) -> None:
        self.issuer = issuer
        self.capture_origin = capture_origin.rstrip("/")
        self._client = client

    def generate_magic_link(self, *, attempt_id: UUID, email: str, now: datetime) -> GeneratedMagicLink:
        try:
            normalized_email = normalize_email(email).value
            response = self._client.auth.admin.generate_link(
                {
                    "type": "magiclink",
                    "email": normalized_email,
                    "options": {"redirect_to": f"{self.capture_origin}/auth/capture"},
                }
            )
            token_hash = _required_text(response.properties.hashed_token)
            generated_at = now.astimezone(timezone.utc)
            return GeneratedMagicLink(
                self.provider,
                attempt_id,
                token_hash,
                f"{self.capture_origin}/auth/capture?{urlencode({'attempt_id': attempt_id, 'token_hash': token_hash})}",
                generated_at,
                generated_at + timedelta(minutes=15),
            )
        except Exception as exc:
            raise IdentityError("auth.provider_unavailable", status=503, recovery="retry_later") from exc

    def verify_magic_link(self, *, attempt_id: UUID, token_hash: str, now: datetime) -> ProviderProof:
        try:
            response = self._client.auth.verify_otp(
                {"type": "magiclink", "token_hash": token_hash}
            )
            user = _required_object(response.user)
            session = _required_object(response.session)
            subject = _required_text(getattr(user, "id", None))
            verified_email = normalize_email(_required_text(getattr(user, "email", None))).value
            if not _required_text(getattr(user, "email_confirmed_at", None)):
                raise IdentityError("auth.link_unavailable", status=410, recovery="request_new_link")
            access_token = _required_text(getattr(session, "access_token", None))
            claims = _access_token_claims(access_token)
            issuer = _required_text(claims.get("iss"))
            if issuer != self.issuer or _required_text(claims.get("sub")) != subject:
                raise IdentityError("auth.link_unavailable", status=410, recovery="request_new_link")
            return ProviderProof(
                self.provider,
                issuer,
                subject,
                verified_email,
                now.astimezone(timezone.utc),
                revocation_handle=access_token,
            )
        except IdentityError:
            raise
        except Exception as exc:
            raise IdentityError("auth.provider_unavailable", status=503, recovery="retry_later") from exc

    def revoke_provider_session(self, handle: str) -> None:
        try:
            self._client.auth.admin.sign_out(handle, scope="global")
        except Exception as exc:
            raise IdentityError("auth.provider_unavailable", status=503, recovery="retry_later") from exc

    def health(self) -> str:
        return "ready"


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not (text := value.strip()):
        raise IdentityError("auth.link_unavailable", status=410, recovery="request_new_link")
    return text


def _required_object(value: object) -> object:
    if value is None:
        raise IdentityError("auth.link_unavailable", status=410, recovery="request_new_link")
    return value


def _access_token_claims(access_token: str) -> dict[str, object]:
    parts = access_token.split(".")
    if len(parts) != 3:
        raise IdentityError("auth.link_unavailable", status=410, recovery="request_new_link")
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    decoded = base64.urlsafe_b64decode(payload)
    claims = json.loads(decoded)
    if not isinstance(claims, dict):
        raise IdentityError("auth.link_unavailable", status=410, recovery="request_new_link")
    return claims
