"""Provider-independent identity records and state invariants."""
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

Role = Literal["user", "operator", "administrator"]
UserStatus = Literal["active", "disabled"]
InvitationStatus = Literal["active", "accepted"]
AttemptState = Literal[
    "pending", "issuing", "issued", "consumed", "superseded", "expired", "failed"
]
SubjectKind = Literal["invitation", "product_user"]


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(slots=True)
class Invitation:
    id: UUID
    normalized_email: str
    status: InvitationStatus = "active"
    accepted_user_id: UUID | None = None
    preload_source: str = "controlled_preload"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    accepted_at: datetime | None = None

    @classmethod
    def new(cls, email: str, *, source: str = "controlled_preload") -> "Invitation":
        return cls(id=uuid4(), normalized_email=email, preload_source=source)


@dataclass(slots=True)
class ProductUser:
    id: UUID
    normalized_email: str
    status: UserStatus = "active"
    disabled_reason: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status_changed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def disable(self, reason: str, *, now: datetime) -> None:
        if not reason or len(reason) > 100:
            raise ValueError("disabled reason must be bounded")
        self.status = "disabled"
        self.disabled_reason = reason
        self.status_changed_at = utc(now)

    def enable(self, *, now: datetime) -> None:
        self.status = "active"
        self.disabled_reason = None
        self.status_changed_at = utc(now)


@dataclass(slots=True)
class ExternalIdentityLink:
    id: UUID
    product_user_id: UUID
    provider: str
    provider_issuer: str
    provider_subject: str
    verified_normalized_email: str
    verified_at: datetime


@dataclass(slots=True)
class RoleAssignment:
    id: UUID
    product_user_id: UUID
    role: Role
    granted_at: datetime
    revoked_at: datetime | None = None
    reason: str = "activation"

    @property
    def active(self) -> bool:
        return self.revoked_at is None


@dataclass(slots=True)
class ProductSession:
    id: UUID
    product_user_id: UUID
    magic_link_attempt_id: UUID
    token_digest: bytes
    last_activity_at: datetime
    revoked_at: datetime | None = None
    revocation_reason: str | None = None

    def is_idle_expired(self, now: datetime) -> bool:
        return utc(now) >= utc(self.last_activity_at) + timedelta(days=7)


@dataclass(slots=True)
class MagicLinkRequest:
    id: UUID
    email_fingerprint: bytes
    origin_fingerprint: bytes
    decision: str
    requested_at: datetime
    purge_after: datetime
    correlation_id: UUID


@dataclass(slots=True)
class MagicLinkAttempt:
    id: UUID
    request_id: UUID
    subject_kind: SubjectKind
    invitation_id: UUID | None
    product_user_id: UUID | None
    job_execution_id: UUID | None = None
    state: AttemptState = "pending"
    provider_generated_at: datetime | None = None
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    consumed_at: datetime | None = None
    superseded_at: datetime | None = None
    superseded_by_id: UUID | None = None
    provider_message_id: str | None = None
    failure_reason: str | None = None

    def current_and_valid(self, now: datetime) -> bool:
        return (
            self.state == "issued"
            and self.expires_at is not None
            and utc(now) < utc(self.expires_at)
            and self.consumed_at is None
            and self.superseded_at is None
        )


@dataclass(frozen=True, slots=True)
class AccessAuditEvent:
    id: UUID
    event_type: str
    result: str
    reason: str
    correlation_id: UUID
    occurred_at: datetime
    actor_user_id: UUID | None = None
    subject_user_id: UUID | None = None
    invitation_id: UUID | None = None
    request_id: UUID | None = None
    attempt_id: UUID | None = None
    session_id: UUID | None = None
    role_assignment_id: UUID | None = None
    action: str | None = None
    policy_version: str | None = None
    provider: str | None = None
    provider_event_id: str | None = None
