"""Closed environment access policy used by deployment gates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


class AccessPolicyViolation(ValueError):
    """Raised when an access request does not match the expected policy."""


@dataclass(frozen=True)
class AccessPolicy:
    allowed_origins: tuple[str, ...]
    public_paths: tuple[str, ...] = (
        "/health",
        "/login",
        "/auth/capture",
        "/auth/confirm",
        "/api/auth/magic-link-requests",
        "/api/webhooks/email",
    )
    require_access_header: bool = True
    audience: str = "umbral-runtime"

    @classmethod
    def default(cls) -> "AccessPolicy":
        return cls(allowed_origins=())

    def is_public_path(self, path: str) -> bool:
        return path in self.public_paths

    def assert_allowed_public_path(self, path: str) -> None:
        if not self.is_public_path(path):
            raise AccessPolicyViolation("path is not in the anonymous allowlist")

    def validate_claims(self, claims: Mapping[str, object], *, now: int) -> None:
        if claims.get("aud") != self.audience:
            raise AccessPolicyViolation("invalid audience")
        expiry = claims.get("exp")
        if not isinstance(expiry, (int, float)) or expiry <= now:
            raise AccessPolicyViolation("expired token")
