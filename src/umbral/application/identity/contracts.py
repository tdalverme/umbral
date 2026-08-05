"""Provider-neutral DTOs and stable identity failures."""
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

NEUTRAL_MESSAGE = "Si la dirección está habilitada, recibirás un enlace para continuar."


@dataclass(frozen=True, slots=True)
class MagicLinkRequestResult:
    status: int = 202
    message: str = NEUTRAL_MESSAGE


@dataclass(frozen=True, slots=True)
class ProviderProof:
    provider: str
    issuer: str
    subject: str
    verified_email: str
    verified_at: datetime
    revocation_handle: str | None = None


@dataclass(frozen=True, slots=True)
class GeneratedMagicLink:
    provider: str
    attempt_id: UUID
    token_hash: str
    capture_url: str
    generated_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class EmailAcceptance:
    provider: str
    message_id: str
    accepted_at: datetime


@dataclass(frozen=True, slots=True)
class SessionResult:
    session_id: UUID
    user_id: UUID
    token: str
    last_activity_at: datetime


@dataclass(frozen=True, slots=True)
class CurrentPrincipal:
    user_id: UUID
    roles: tuple[str, ...]
    last_activity_at: datetime


class IdentityError(Exception):
    """Stable, transport-neutral identity failure."""

    def __init__(self, code: str, *, status: int, recovery: str, detail: str | None = None) -> None:
        self.code = code
        self.status = status
        self.recovery = recovery
        self.detail = detail
        super().__init__(code)


def link_unavailable(reason: str = "link_invalid") -> IdentityError:
    return IdentityError("auth.link_unavailable", status=410, recovery="request_new_link", detail=reason)


def access_denied() -> IdentityError:
    return IdentityError("auth.access_denied", status=403, recovery="contact_support")
