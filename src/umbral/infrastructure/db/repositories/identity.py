"""Deterministic repository used by local adapters and application tests.

The same shape is implemented by the PostgreSQL adapter in production; the
in-memory implementation keeps unit/contract tests independent of a database.
"""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import hmac
import threading
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

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
from umbral.infrastructure.db.models.identity import (
    AccessAuditEvent as AccessAuditEventRow,
)
from umbral.infrastructure.db.models.identity import (
    MagicLinkRequest as MagicLinkRequestRow,
)
from umbral.infrastructure.db.models.identity import (
    ProductSession as ProductSessionRow,
)
from umbral.infrastructure.db.models.identity import (
    ProductUser as ProductUserRow,
)
from umbral.infrastructure.db.models.identity import (
    RoleAssignment as RoleAssignmentRow,
)


class InMemoryIdentityStore:
    def __init__(self, *, fingerprint_key: bytes = b"local-identity-key") -> None:
        self.invitations: dict[UUID, Invitation] = {}
        self.users: dict[UUID, ProductUser] = {}
        self.links: dict[UUID, ExternalIdentityLink] = {}
        self.roles: dict[UUID, RoleAssignment] = {}
        self.requests: dict[UUID, MagicLinkRequest] = {}
        self.attempts: dict[UUID, MagicLinkAttempt] = {}
        self.sessions: dict[UUID, ProductSession] = {}
        self.audits: list[AccessAuditEvent] = []
        self._key = fingerprint_key
        self.lock = threading.RLock()

    def fingerprint(self, value: str) -> bytes:
        return hmac.new(self._key, value.encode(), hashlib.sha256).digest()

    def invitation_for_email(self, email: str) -> Invitation | None:
        return next((item for item in self.invitations.values() if item.normalized_email == email), None)

    def user_for_email(self, email: str) -> ProductUser | None:
        return next((item for item in self.users.values() if item.normalized_email == email), None)

    def link_for_subject(self, provider: str, issuer: str, subject: str) -> ExternalIdentityLink | None:
        return next((item for item in self.links.values() if item.provider == provider and item.provider_issuer == issuer and item.provider_subject == subject), None)

    def active_roles(self, user_id: UUID) -> set[str]:
        return {item.role for item in self.roles.values() if item.product_user_id == user_id and item.active}

    def current_attempt(self, *, invitation_id: UUID | None = None, product_user_id: UUID | None = None) -> MagicLinkAttempt | None:
        candidates = [item for item in self.attempts.values() if item.state == "issued"]
        if invitation_id is not None:
            candidates = [item for item in candidates if item.invitation_id == invitation_id]
        if product_user_id is not None:
            candidates = [item for item in candidates if item.product_user_id == product_user_id]
        return max(candidates, key=lambda item: item.issued_at or datetime.min.replace(tzinfo=timezone.utc), default=None)

    def recent_requests(self, fingerprint: bytes, *, now: datetime, field: str) -> int:
        threshold = now.astimezone(timezone.utc) - timedelta(minutes=15)
        return sum(1 for item in self.requests.values() if getattr(item, field) == fingerprint and item.requested_at > threshold)


class PostgresIdentityRepository:
    """Small persistence seam for production identity transactions.

    The caller owns the surrounding transaction.  Limiter arbitration locks a
    stable email/origin key and obtains the timestamp from PostgreSQL so two
    concurrent requests cannot both pass a stale application-clock check.
    """

    _LIMITER_FIELDS = {"email_fingerprint", "origin_fingerprint"}

    def __init__(self, session: Session) -> None:
        self.session = session

    def database_now(self) -> datetime:
        value = self.session.scalar(select(func.current_timestamp()))
        if value is None:
            raise RuntimeError("database clock unavailable")
        return value

    def reserve_request(
        self,
        *,
        email_fingerprint: bytes,
        origin_fingerprint: bytes,
        email_limit: int,
        origin_limit: int,
        correlation_id: UUID,
        decision: str,
    ) -> bool:
        """Reserve a request row atomically, returning whether it is eligible."""

        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": email_fingerprint.hex()},
        )
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": origin_fingerprint.hex()},
        )
        now = self.database_now()
        window = text("current_timestamp - interval '15 minutes'")
        email_count = self._count_recent("email_fingerprint", email_fingerprint, window)
        origin_count = self._count_recent("origin_fingerprint", origin_fingerprint, window)
        allowed = email_count < email_limit and origin_count < origin_limit
        self.session.add(
            MagicLinkRequestRow(
                email_fingerprint=email_fingerprint,
                origin_fingerprint=origin_fingerprint,
                decision=decision if allowed else "rejected_rate_limit",
                requested_at=now,
                purge_after=now + timedelta(hours=24),
                correlation_id=correlation_id,
            )
        )
        return allowed

    def _count_recent(self, field: str, fingerprint: bytes, window: object) -> int:
        if field not in self._LIMITER_FIELDS:
            raise ValueError("unsupported limiter field")
        column = getattr(MagicLinkRequestRow, field)
        value = self.session.scalar(
            select(func.count())
            .select_from(MagicLinkRequestRow)
            .where(column == fingerprint, MagicLinkRequestRow.requested_at > window)
        )
        return int(value or 0)

    def find_user_by_email(self, normalized_email: str) -> ProductUserRow | None:
        return self.session.scalar(select(ProductUserRow).where(ProductUserRow.normalized_email == normalized_email))

    def current_roles(self, user_id: UUID) -> set[str]:
        rows = self.session.scalars(
            select(RoleAssignmentRow.role).where(
                RoleAssignmentRow.product_user_id == user_id,
                RoleAssignmentRow.revoked_at.is_(None),
            )
        )
        return set(rows)

    def session_by_digest(self, token_digest: bytes) -> ProductSessionRow | None:
        return self.session.scalar(select(ProductSessionRow).where(ProductSessionRow.token_digest == token_digest))

    def append_audit(self, event: AccessAuditEvent) -> None:
        """Stage one append-only audit row; the caller owns commit/rollback."""

        self.session.add(
            AccessAuditEventRow(
                id=event.id,
                event_type=event.event_type,
                result=event.result,
                reason=event.reason,
                action=event.action,
                policy_version=event.policy_version,
                actor_kind="operator" if event.actor_user_id else "system",
                actor_user_id=event.actor_user_id,
                subject_user_id=event.subject_user_id,
                invitation_id=event.invitation_id,
                request_id=event.request_id,
                attempt_id=event.attempt_id,
                session_id=event.session_id,
                role_assignment_id=event.role_assignment_id,
                provider=event.provider,
                provider_event_id=event.provider_event_id,
                environment="local",
                correlation_id=event.correlation_id,
                occurred_at=event.occurred_at,
            )
        )
