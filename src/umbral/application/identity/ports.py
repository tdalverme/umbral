"""Narrow provider and persistence ports; SDK types do not cross this seam."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from umbral.application.identity.contracts import (
    EmailAcceptance,
    GeneratedMagicLink,
    ProviderProof,
)

if TYPE_CHECKING:
    from umbral.domain.identity.models import (
        AccessAuditEvent,
        ExternalIdentityLink,
        Invitation,
        MagicLinkAttempt,
        MagicLinkRequest,
        ProductSession,
        ProductUser,
        RoleAssignment,
    )


class IdentityProofPort(Protocol):
    provider: str
    issuer: str

    def generate_magic_link(self, *, attempt_id: UUID, email: str, now: datetime) -> GeneratedMagicLink: ...

    def verify_magic_link(self, *, attempt_id: UUID, token_hash: str, now: datetime) -> ProviderProof: ...

    def revoke_provider_session(self, handle: str) -> None: ...


class EmailPort(Protocol):
    provider: str

    def send_magic_link(self, *, attempt_id: UUID, normalized_email: str, capture_url: str, expires_at: datetime, idempotency_key: str, now: datetime) -> EmailAcceptance: ...

    def verify_webhook(self, *, raw_body: bytes, headers: Mapping[str, str], received_at: datetime) -> Mapping[str, str] | None: ...


class IdentityStore(Protocol):
    invitations: dict[UUID, Invitation]
    users: dict[UUID, ProductUser]
    links: dict[UUID, ExternalIdentityLink]
    roles: dict[UUID, RoleAssignment]
    requests: dict[UUID, MagicLinkRequest]
    attempts: dict[UUID, MagicLinkAttempt]
    sessions: dict[UUID, ProductSession]
    audits: list[AccessAuditEvent]
    lock: Any

    def fingerprint(self, value: str) -> bytes: ...

    def invitation_for_email(self, email: str) -> Invitation | None: ...

    def user_for_email(self, email: str) -> ProductUser | None: ...

    def link_for_subject(self, provider: str, issuer: str, subject: str) -> ExternalIdentityLink | None: ...

    def active_roles(self, user_id: UUID) -> set[str]: ...

    def current_attempt(self, *, invitation_id: UUID | None = None, product_user_id: UUID | None = None) -> MagicLinkAttempt | None: ...

    def recent_requests(self, fingerprint: bytes, *, now: datetime, field: str) -> int: ...
