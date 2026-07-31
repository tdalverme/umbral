"""Deterministic identity-proof fake used by tests and local development."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from umbral.application.identity.contracts import (
    GeneratedMagicLink,
    IdentityError,
    ProviderProof,
)
from umbral.domain.identity.email import normalize_email


class FakeIdentityProvider:
    provider = "fake"

    def __init__(self, *, issuer: str = "fake://local", capture_origin: str = "http://localhost:3000") -> None:
        self.issuer = issuer
        self.capture_origin = capture_origin.rstrip("/")
        self._tokens: dict[UUID, tuple[str, str, datetime]] = {}
        self._subjects: dict[str, str] = {}
        self.fail_generation = False
        self.fail_verification = False
        self.revoked: list[str] = []

    def generate_magic_link(self, *, attempt_id: UUID, email: str, now: datetime) -> GeneratedMagicLink:
        if self.fail_generation:
            raise IdentityError("auth.provider_unavailable", status=503, recovery="retry_later")
        generated_at = now.astimezone(timezone.utc)
        expires_at = generated_at + timedelta(minutes=15)
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        normalized = normalize_email(email).value
        self._tokens[attempt_id] = (token_hash, normalized, expires_at)
        self._subjects.setdefault(
            normalized,
            "fake-subject-" + hashlib.sha256(normalized.encode()).hexdigest()[:24],
        )
        return GeneratedMagicLink(
            provider=self.provider,
            attempt_id=attempt_id,
            token_hash=token_hash,
            capture_url=f"{self.capture_origin}/auth/capture?attempt_id={attempt_id}&token_hash={token_hash}",
            generated_at=generated_at,
            expires_at=expires_at,
        )

    def verify_magic_link(self, *, attempt_id: UUID, token_hash: str, now: datetime) -> ProviderProof:
        if self.fail_verification:
            raise IdentityError("auth.provider_unavailable", status=503, recovery="retry_later")
        record = self._tokens.get(attempt_id)
        if record is None or not secrets.compare_digest(record[0], token_hash):
            raise IdentityError("auth.link_unavailable", status=410, recovery="request_new_link")
        if now.astimezone(timezone.utc) >= record[2]:
            raise IdentityError("auth.link_unavailable", status=410, recovery="request_new_link")
        return ProviderProof(
            provider=self.provider,
            issuer=self.issuer,
            subject=self._subjects[record[1]],
            verified_email=record[1],
            verified_at=now.astimezone(timezone.utc),
            revocation_handle=f"rev-{attempt_id}",
        )

    def revoke_provider_session(self, handle: str) -> None:
        self.revoked.append(handle)

    def health(self) -> str:
        return "degraded" if self.fail_generation or self.fail_verification else "ready"
