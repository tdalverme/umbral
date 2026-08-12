"""Deterministic repository used by local adapters and application tests.

The same shape is implemented by the PostgreSQL adapter in production; the
in-memory implementation keeps unit/contract tests independent of a database.
"""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import hmac
import threading
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, cast
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from umbral.domain.identity.events import validate_event
from umbral.domain.identity.models import (
    AccessAuditEvent,
    ExternalIdentityLink,
    IdentityExportLink,
    IdentityExportRecord,
    IdentityReport,
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
    ExternalIdentityLink as ExternalIdentityLinkRow,
)
from umbral.infrastructure.db.models.identity import (
    IdentityInvitation as IdentityInvitationRow,
)
from umbral.infrastructure.db.models.identity import (
    MagicLinkAttempt as MagicLinkAttemptRow,
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


class SqlAlchemyIdentityStore:
    """PostgreSQL identity store with a single owned session per transaction."""

    _LIMITER_FIELDS = {"email_fingerprint", "origin_fingerprint"}

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        fingerprint_key: bytes = b"local-identity-key",
        environment: str = "local",
    ) -> None:
        self._session_factory = session_factory
        self._key = fingerprint_key
        self._environment = environment
        self._active_session: ContextVar[Session | None] = ContextVar(
            "identity_session", default=None
        )

    @contextmanager
    def transaction(self) -> Iterator[None]:
        existing = self._active_session.get()
        if existing is not None:
            with existing.begin_nested():
                yield
            return
        session = self._session_factory()
        token = self._active_session.set(session)
        try:
            yield
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            self._active_session.reset(token)
            session.close()

    @contextmanager
    def _read_session(self) -> Iterator[Session]:
        active = self._active_session.get()
        if active is not None:
            yield active
            return
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    def _write_session(self) -> Session:
        session = self._active_session.get()
        if session is None:
            raise RuntimeError("identity writes require an active transaction")
        return session

    def fingerprint(self, value: str) -> bytes:
        return hmac.new(self._key, value.encode(), hashlib.sha256).digest()

    def _upsert(self, row_type: type[Any], values: dict[str, Any]) -> None:
        statement = insert(row_type).values(**values)
        updates = {key: value for key, value in values.items() if key != "id"}
        self._write_session().execute(
            statement.on_conflict_do_update(index_elements=["id"], set_=updates)
        )

    @staticmethod
    def _audit_fields(event: AccessAuditEvent, environment: str) -> dict[str, Any]:
        return {
            "id": event.id,
            "event_type": event.event_type,
            "result": event.result,
            "reason": event.reason,
            "action": event.action,
            "policy_version": event.policy_version,
            "actor_kind": "operator" if event.actor_user_id else "system",
            "actor_user_id": event.actor_user_id,
            "subject_user_id": event.subject_user_id,
            "invitation_id": event.invitation_id,
            "request_id": event.request_id,
            "attempt_id": event.attempt_id,
            "session_id": event.session_id,
            "role_assignment_id": event.role_assignment_id,
            "provider": event.provider,
            "provider_event_id": event.provider_event_id,
            "environment": environment,
            "correlation_id": event.correlation_id,
            "occurred_at": event.occurred_at,
        }

    @staticmethod
    def _row_audit(row: AccessAuditEventRow) -> AccessAuditEvent:
        return AccessAuditEvent(
            row.id,
            row.event_type,
            row.result,
            row.reason,
            row.correlation_id,
            row.occurred_at,
            actor_user_id=row.actor_user_id,
            subject_user_id=row.subject_user_id,
            invitation_id=row.invitation_id,
            request_id=row.request_id,
            attempt_id=row.attempt_id,
            session_id=row.session_id,
            role_assignment_id=row.role_assignment_id,
            action=row.action,
            policy_version=row.policy_version,
            provider=row.provider,
            provider_event_id=row.provider_event_id,
        )

    def invitation_for_email(self, email: str) -> Invitation | None:
        with self._read_session() as session:
            row = session.scalar(
                select(IdentityInvitationRow).where(
                    IdentityInvitationRow.normalized_email == email
                )
            )
            return self._invitation(row) if row else None

    def invitation(self, invitation_id: UUID) -> Invitation | None:
        with self._read_session() as session:
            query = select(IdentityInvitationRow).where(
                IdentityInvitationRow.id == invitation_id
            )
            if self._active_session.get() is not None:
                query = query.with_for_update()
            row = session.scalar(query)
            return self._invitation(row) if row else None

    def save_invitation(self, invitation: Invitation) -> None:
        self._upsert(
            IdentityInvitationRow,
            {
                "id": invitation.id,
                "normalized_email": invitation.normalized_email,
                "status": invitation.status,
                "accepted_user_id": invitation.accepted_user_id,
                "accepted_at": invitation.accepted_at,
                "preload_source": invitation.preload_source,
                "preload_actor_kind": "deployment",
                "preload_actor_id": "identity-store",
                "created_at": invitation.created_at,
                "updated_at": invitation.accepted_at or invitation.created_at,
                "actor_kind": "system",
                "source": "identity_store",
                "correlation_id": uuid4(),
            },
        )

    @staticmethod
    def _invitation(row: IdentityInvitationRow) -> Invitation:
        return Invitation(
            row.id,
            row.normalized_email,
            cast(Any, row.status),
            row.accepted_user_id,
            row.preload_source,
            row.created_at,
            row.accepted_at,
        )

    def user(self, user_id: UUID) -> ProductUser | None:
        with self._read_session() as session:
            query = select(ProductUserRow).where(ProductUserRow.id == user_id)
            if self._active_session.get() is not None:
                query = query.with_for_update()
            row = session.scalar(query)
            return self._user(row) if row else None

    def user_for_email(self, email: str) -> ProductUser | None:
        with self._read_session() as session:
            row = session.scalar(
                select(ProductUserRow).where(ProductUserRow.normalized_email == email)
            )
            return self._user(row) if row else None

    def save_user(self, user: ProductUser) -> None:
        self._upsert(
            ProductUserRow,
            {
                "id": user.id,
                "normalized_email": user.normalized_email,
                "status": user.status,
                "disabled_reason": user.disabled_reason,
                "status_changed_at": user.status_changed_at,
                "status_change_source": "identity_store",
                "created_at": user.created_at,
                "updated_at": user.status_changed_at,
                "actor_kind": "system",
                "source": "identity_store",
                "correlation_id": uuid4(),
            },
        )

    @staticmethod
    def _user(row: ProductUserRow) -> ProductUser:
        return ProductUser(
            row.id,
            row.normalized_email,
            cast(Any, row.status),
            row.disabled_reason,
            row.created_at,
            row.status_changed_at,
        )

    def link_for_subject(
        self, provider: str, issuer: str, subject: str
    ) -> ExternalIdentityLink | None:
        with self._read_session() as session:
            row = session.scalar(
                select(ExternalIdentityLinkRow).where(
                    ExternalIdentityLinkRow.provider == provider,
                    ExternalIdentityLinkRow.provider_issuer == issuer,
                    ExternalIdentityLinkRow.provider_subject == subject,
                )
            )
            return self._link(row) if row else None

    def save_link(self, link: ExternalIdentityLink) -> None:
        self._upsert(
            ExternalIdentityLinkRow,
            {
                "id": link.id,
                "product_user_id": link.product_user_id,
                "provider": link.provider,
                "provider_issuer": link.provider_issuer,
                "provider_subject": link.provider_subject,
                "verified_normalized_email": link.verified_normalized_email,
                "verified_at": link.verified_at,
                "linked_at": link.verified_at,
                "created_at": link.verified_at,
                "updated_at": link.verified_at,
                "actor_kind": "system",
                "source": "identity_store",
                "correlation_id": uuid4(),
            },
        )

    @staticmethod
    def _link(row: ExternalIdentityLinkRow) -> ExternalIdentityLink:
        return ExternalIdentityLink(
            row.id,
            row.product_user_id,
            row.provider,
            row.provider_issuer,
            row.provider_subject,
            row.verified_normalized_email,
            row.verified_at,
        )

    def active_roles(self, user_id: UUID) -> set[str]:
        with self._read_session() as session:
            return set(
                session.scalars(
                    select(RoleAssignmentRow.role).where(
                        RoleAssignmentRow.product_user_id == user_id,
                        RoleAssignmentRow.revoked_at.is_(None),
                    )
                )
            )

    def active_role(self, user_id: UUID, role: str) -> RoleAssignment | None:
        with self._read_session() as session:
            query = select(RoleAssignmentRow).where(
                RoleAssignmentRow.product_user_id == user_id,
                RoleAssignmentRow.role == role,
                RoleAssignmentRow.revoked_at.is_(None),
            )
            if self._active_session.get() is not None:
                query = query.with_for_update()
            row = session.scalar(query)
            return self._role(row) if row else None

    def has_active_administrator(self) -> bool:
        with self._read_session() as session:
            return (
                session.scalar(
                    select(RoleAssignmentRow.id)
                    .where(
                        RoleAssignmentRow.role == "administrator",
                        RoleAssignmentRow.revoked_at.is_(None),
                    )
                    .limit(1)
                )
                is not None
            )

    def save_role(self, role: RoleAssignment) -> None:
        self._upsert(
            RoleAssignmentRow,
            {
                "id": role.id,
                "product_user_id": role.product_user_id,
                "role": role.role,
                "granted_at": role.granted_at,
                "grant_actor_kind": "system",
                "grant_actor_id": "identity-store",
                "grant_reason": role.reason,
                "revoked_at": role.revoked_at,
                "revoke_reason": role.reason if role.revoked_at else None,
                "created_at": role.granted_at,
                "updated_at": role.revoked_at or role.granted_at,
                "actor_kind": "system",
                "source": "identity_store",
                "correlation_id": uuid4(),
            },
        )

    @staticmethod
    def _role(row: RoleAssignmentRow) -> RoleAssignment:
        return RoleAssignment(
            row.id,
            row.product_user_id,
            cast(Any, row.role),
            row.granted_at,
            row.revoked_at,
            row.grant_reason,
        )

    def save_request(self, request: MagicLinkRequest) -> None:
        self._upsert(
            MagicLinkRequestRow,
            {
                "id": request.id,
                "email_fingerprint": request.email_fingerprint,
                "origin_fingerprint": request.origin_fingerprint,
                "decision": request.decision,
                "requested_at": request.requested_at,
                "purge_after": request.purge_after,
                "correlation_id": request.correlation_id,
            },
        )

    def request(self, request_id: UUID) -> MagicLinkRequest | None:
        with self._read_session() as session:
            row = session.get(MagicLinkRequestRow, request_id)
            return self._request(row) if row else None

    @staticmethod
    def _request(row: MagicLinkRequestRow) -> MagicLinkRequest:
        return MagicLinkRequest(
            row.id,
            row.email_fingerprint,
            row.origin_fingerprint,
            row.decision,
            row.requested_at,
            row.purge_after,
            row.correlation_id,
        )

    def current_attempt(
        self, *, invitation_id: UUID | None = None, product_user_id: UUID | None = None
    ) -> MagicLinkAttempt | None:
        self._lock_attempt_subjects(invitation_id, product_user_id)
        query = select(MagicLinkAttemptRow).where(MagicLinkAttemptRow.state == "issued")
        if invitation_id is not None:
            query = query.where(MagicLinkAttemptRow.invitation_id == invitation_id)
        if product_user_id is not None:
            query = query.where(MagicLinkAttemptRow.product_user_id == product_user_id)
        query = query.order_by(MagicLinkAttemptRow.issued_at.desc()).limit(1)
        if self._active_session.get() is not None:
            query = query.with_for_update()
        with self._read_session() as session:
            row = session.scalar(query)
            return self._attempt(row) if row else None

    def _lock_attempt_subjects(
        self, invitation_id: UUID | None, product_user_id: UUID | None
    ) -> None:
        session = self._active_session.get()
        if session is None:
            return
        keys = []
        if invitation_id is not None:
            keys.append(f"identity-attempt:invitation:{invitation_id}")
        if product_user_id is not None:
            keys.append(f"identity-attempt:user:{product_user_id}")
        for key in sorted(keys):
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": key},
            )

    def save_attempt(self, attempt: MagicLinkAttempt) -> None:
        self._upsert(
            MagicLinkAttemptRow,
            {
                "id": attempt.id,
                "request_id": attempt.request_id,
                "subject_kind": attempt.subject_kind,
                "invitation_id": attempt.invitation_id,
                "product_user_id": attempt.product_user_id,
                "job_execution_id": attempt.job_execution_id,
                "state": attempt.state,
                "provider_generated_at": attempt.provider_generated_at,
                "issued_at": attempt.issued_at,
                "expires_at": attempt.expires_at,
                "consumed_at": attempt.consumed_at,
                "superseded_at": attempt.superseded_at,
                "superseded_by_id": attempt.superseded_by_id,
                "provider_message_id": attempt.provider_message_id,
                "failure_reason": attempt.failure_reason,
                "created_at": attempt.provider_generated_at
                or attempt.issued_at
                or datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "actor_kind": "system",
                "source": "identity_store",
                "correlation_id": uuid4(),
            },
        )

    def attempt(self, attempt_id: UUID) -> MagicLinkAttempt | None:
        with self._read_session() as session:
            query = select(MagicLinkAttemptRow).where(
                MagicLinkAttemptRow.id == attempt_id
            )
            if self._active_session.get() is not None:
                query = query.with_for_update()
            row = session.scalar(query)
            return self._attempt(row) if row else None

    def attempt_for_provider_message(self, message_id: str) -> MagicLinkAttempt | None:
        with self._read_session() as session:
            row = session.scalar(
                select(MagicLinkAttemptRow).where(
                    MagicLinkAttemptRow.provider_message_id == message_id
                )
            )
            return self._attempt(row) if row else None

    @staticmethod
    def _attempt(row: MagicLinkAttemptRow) -> MagicLinkAttempt:
        return MagicLinkAttempt(
            row.id,
            row.request_id,
            cast(Any, row.subject_kind),
            row.invitation_id,
            row.product_user_id,
            row.job_execution_id,
            cast(Any, row.state),
            row.provider_generated_at,
            row.issued_at,
            row.expires_at,
            row.consumed_at,
            row.superseded_at,
            row.superseded_by_id,
            row.provider_message_id,
            row.failure_reason,
        )

    def session_by_digest(self, digest: bytes) -> ProductSession | None:
        with self._read_session() as session:
            query = select(ProductSessionRow).where(
                ProductSessionRow.token_digest == digest
            )
            if self._active_session.get() is not None:
                query = query.with_for_update()
            row = session.scalar(query)
            return self._session(row) if row else None

    def save_session(self, product_session: ProductSession) -> None:
        self._upsert(
            ProductSessionRow,
            {
                "id": product_session.id,
                "product_user_id": product_session.product_user_id,
                "magic_link_attempt_id": product_session.magic_link_attempt_id,
                "token_digest": product_session.token_digest,
                "last_activity_at": product_session.last_activity_at,
                "revoked_at": product_session.revoked_at,
                "revocation_reason": product_session.revocation_reason,
                "created_at": product_session.last_activity_at,
                "updated_at": product_session.revoked_at
                or product_session.last_activity_at,
                "actor_kind": "system",
                "source": "identity_store",
                "correlation_id": uuid4(),
            },
        )

    @staticmethod
    def _session(row: ProductSessionRow) -> ProductSession:
        return ProductSession(
            row.id,
            row.product_user_id,
            row.magic_link_attempt_id,
            row.token_digest,
            row.last_activity_at,
            row.revoked_at,
            row.revocation_reason,
        )

    def append_audit(self, event: AccessAuditEvent) -> None:
        self._write_session().execute(
            insert(AccessAuditEventRow).values(
                **self._audit_fields(event, self._environment)
            )
        )

    def append_provider_audit_once(
        self, provider: str, event_id: str, audit_event: AccessAuditEvent | None
    ) -> bool:
        event = audit_event or AccessAuditEvent(
            uuid4(),
            "provider.event_ignored.v1",
            "observed",
            "ignored",
            uuid4(),
            datetime.now(timezone.utc),
            provider=provider,
            provider_event_id=event_id,
        )
        validate_event(
            event_type=event.event_type,
            result=event.result,
            reason=event.reason,
            fields={"provider": provider, "provider_event_id": event_id},
        )
        values = self._audit_fields(event, self._environment)
        values["provider"] = provider
        values["provider_event_id"] = event_id
        inserted_id = self._write_session().scalar(
            insert(AccessAuditEventRow)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_access_audit_provider_event")
            .returning(AccessAuditEventRow.id)
        )
        return inserted_id is not None

    def audit_events(self) -> tuple[AccessAuditEvent, ...]:
        with self._read_session() as session:
            return tuple(
                self._row_audit(row)
                for row in session.scalars(
                    select(AccessAuditEventRow).order_by(
                        AccessAuditEventRow.occurred_at, AccessAuditEventRow.id
                    )
                )
            )

    def identity_report(self) -> IdentityReport:
        with self._read_session() as session:
            event_counts = tuple(
                (event_type, int(count))
                for event_type, count in session.execute(
                    select(AccessAuditEventRow.event_type, func.count())
                    .group_by(AccessAuditEventRow.event_type)
                    .order_by(AccessAuditEventRow.event_type)
                )
            )
            reason_counts = tuple(
                (reason, int(count))
                for reason, count in session.execute(
                    select(AccessAuditEventRow.reason, func.count())
                    .group_by(AccessAuditEventRow.reason)
                    .order_by(AccessAuditEventRow.reason)
                )
            )
            user_count = int(
                session.scalar(select(func.count()).select_from(ProductUserRow)) or 0
            )
            session_count = int(
                session.scalar(select(func.count()).select_from(ProductSessionRow)) or 0
            )
        return IdentityReport(event_counts, reason_counts, user_count, session_count)

    def exportable_identity_views(self) -> tuple[IdentityExportRecord, ...]:
        with self._read_session() as session:
            users = tuple(
                session.execute(
                    select(ProductUserRow.id, ProductUserRow.status).order_by(
                        ProductUserRow.id
                    )
                )
            )
            roles_by_user: dict[UUID, list[str]] = {}
            for user_id, role in session.execute(
                select(RoleAssignmentRow.product_user_id, RoleAssignmentRow.role)
                .where(RoleAssignmentRow.revoked_at.is_(None))
                .order_by(RoleAssignmentRow.product_user_id, RoleAssignmentRow.role)
            ):
                roles_by_user.setdefault(user_id, []).append(role)
            links_by_user: dict[UUID, list[IdentityExportLink]] = {}
            for user_id, provider, issuer, subject in session.execute(
                select(
                    ExternalIdentityLinkRow.product_user_id,
                    ExternalIdentityLinkRow.provider,
                    ExternalIdentityLinkRow.provider_issuer,
                    ExternalIdentityLinkRow.provider_subject,
                ).order_by(
                    ExternalIdentityLinkRow.product_user_id,
                    ExternalIdentityLinkRow.provider,
                    ExternalIdentityLinkRow.provider_subject,
                )
            ):
                links_by_user.setdefault(user_id, []).append(
                    IdentityExportLink(provider, issuer, subject)
                )
        return tuple(
            IdentityExportRecord(
                user_id=user_id,
                status=cast(Any, status),
                roles=tuple(roles_by_user.get(user_id, [])),
                links=tuple(links_by_user.get(user_id, [])),
            )
            for user_id, status in users
        )

    def exportable_identities(
        self,
    ) -> tuple[tuple[ProductUser, tuple[ExternalIdentityLink, ...]], ...]:
        with self._read_session() as session:
            users = list(
                session.scalars(select(ProductUserRow).order_by(ProductUserRow.id))
            )
            links = list(
                session.scalars(
                    select(ExternalIdentityLinkRow).order_by(ExternalIdentityLinkRow.id)
                )
            )
        return tuple(
            (
                self._user(user),
                tuple(
                    self._link(link)
                    for link in links
                    if link.product_user_id == user.id
                ),
            )
            for user in users
        )

    def session_count(self) -> int:
        with self._read_session() as session:
            return int(
                session.scalar(select(func.count()).select_from(ProductSessionRow)) or 0
            )

    def purge_requests_before(self, cutoff: datetime) -> int:
        session = self._write_session()
        expiring = select(MagicLinkRequestRow.id).where(
            MagicLinkRequestRow.purge_after <= cutoff
        )
        session.execute(
            delete(MagicLinkAttemptRow).where(
                MagicLinkAttemptRow.request_id.in_(expiring)
            )
        )
        session.execute(
            update(AccessAuditEventRow)
            .where(AccessAuditEventRow.request_id.in_(expiring))
            .values(request_id=None)
        )
        result = session.execute(
            delete(MagicLinkRequestRow).where(MagicLinkRequestRow.purge_after <= cutoff)
        )
        return int(getattr(result, "rowcount", 0) or 0)

    def recent_requests(self, fingerprint: bytes, *, now: datetime, field: str) -> int:
        if field not in self._LIMITER_FIELDS:
            raise ValueError("unsupported limiter field")
        session = self._write_session()
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"identity-rate:{field}:{fingerprint.hex()}"},
        )
        column = getattr(MagicLinkRequestRow, field)
        threshold = now.astimezone(timezone.utc) - timedelta(minutes=15)
        return int(
            session.scalar(
                select(func.count())
                .select_from(MagicLinkRequestRow)
                .where(
                    column == fingerprint, MagicLinkRequestRow.requested_at > threshold
                )
            )
            or 0
        )


class InMemoryIdentityStore:
    def __init__(self, *, fingerprint_key: bytes = b"local-identity-key") -> None:
        self._invitations: dict[UUID, Invitation] = {}
        self._users: dict[UUID, ProductUser] = {}
        self._links: dict[UUID, ExternalIdentityLink] = {}
        self._roles: dict[UUID, RoleAssignment] = {}
        self._requests: dict[UUID, MagicLinkRequest] = {}
        self._attempts: dict[UUID, MagicLinkAttempt] = {}
        self._sessions: dict[UUID, ProductSession] = {}
        self._audits: list[AccessAuditEvent] = []
        self._provider_events: set[tuple[str, str]] = set()
        self._key = fingerprint_key
        self._lock = threading.RLock()

    def fingerprint(self, value: str) -> bytes:
        return hmac.new(self._key, value.encode(), hashlib.sha256).digest()

    def invitation_for_email(self, email: str) -> Invitation | None:
        return next(
            (
                item
                for item in self._invitations.values()
                if item.normalized_email == email
            ),
            None,
        )

    def invitation(self, invitation_id: UUID) -> Invitation | None:
        return self._invitations.get(invitation_id)

    def save_invitation(self, invitation: Invitation) -> None:
        self._invitations[invitation.id] = invitation

    def user(self, user_id: UUID) -> ProductUser | None:
        return self._users.get(user_id)

    def user_for_email(self, email: str) -> ProductUser | None:
        return next(
            (item for item in self._users.values() if item.normalized_email == email),
            None,
        )

    def save_user(self, user: ProductUser) -> None:
        self._users[user.id] = user

    def link_for_subject(
        self, provider: str, issuer: str, subject: str
    ) -> ExternalIdentityLink | None:
        return next(
            (
                item
                for item in self._links.values()
                if item.provider == provider
                and item.provider_issuer == issuer
                and item.provider_subject == subject
            ),
            None,
        )

    def save_link(self, link: ExternalIdentityLink) -> None:
        self._links[link.id] = link

    def active_roles(self, user_id: UUID) -> set[str]:
        return {
            item.role
            for item in self._roles.values()
            if item.product_user_id == user_id and item.active
        }

    def active_role(self, user_id: UUID, role: str) -> RoleAssignment | None:
        return next(
            (
                item
                for item in self._roles.values()
                if item.product_user_id == user_id and item.role == role and item.active
            ),
            None,
        )

    def has_active_administrator(self) -> bool:
        return any(
            item.role == "administrator" and item.active
            for item in self._roles.values()
        )

    def save_role(self, role: RoleAssignment) -> None:
        self._roles[role.id] = role

    def save_request(self, request: MagicLinkRequest) -> None:
        self._requests[request.id] = request

    def request(self, request_id: UUID) -> MagicLinkRequest | None:
        return self._requests.get(request_id)

    def current_attempt(
        self, *, invitation_id: UUID | None = None, product_user_id: UUID | None = None
    ) -> MagicLinkAttempt | None:
        candidates = [
            item for item in self._attempts.values() if item.state == "issued"
        ]
        if invitation_id is not None:
            candidates = [
                item for item in candidates if item.invitation_id == invitation_id
            ]
        if product_user_id is not None:
            candidates = [
                item for item in candidates if item.product_user_id == product_user_id
            ]
        return max(
            candidates,
            key=lambda item: (
                item.issued_at or datetime.min.replace(tzinfo=timezone.utc)
            ),
            default=None,
        )

    def recent_requests(self, fingerprint: bytes, *, now: datetime, field: str) -> int:
        threshold = now.astimezone(timezone.utc) - timedelta(minutes=15)
        return sum(
            1
            for item in self._requests.values()
            if getattr(item, field) == fingerprint and item.requested_at > threshold
        )

    def save_attempt(self, attempt: MagicLinkAttempt) -> None:
        self._attempts[attempt.id] = attempt

    def attempt(self, attempt_id: UUID) -> MagicLinkAttempt | None:
        return self._attempts.get(attempt_id)

    def attempt_for_provider_message(self, message_id: str) -> MagicLinkAttempt | None:
        return next(
            (
                item
                for item in self._attempts.values()
                if item.provider_message_id == message_id
            ),
            None,
        )

    def session_by_digest(self, digest: bytes) -> ProductSession | None:
        return next(
            (
                item
                for item in self._sessions.values()
                if hmac.compare_digest(item.token_digest, digest)
            ),
            None,
        )

    def save_session(self, session: ProductSession) -> None:
        self._sessions[session.id] = session

    def append_audit(self, event: AccessAuditEvent) -> None:
        self._audits.append(event)

    def append_provider_audit_once(
        self, provider: str, event_id: str, audit_event: AccessAuditEvent | None
    ) -> bool:
        key = (provider, event_id)
        if key in self._provider_events:
            return False
        self._provider_events.add(key)
        if audit_event is not None:
            self.append_audit(audit_event)
        return True

    def audit_events(self) -> tuple[AccessAuditEvent, ...]:
        return tuple(self._audits)

    def identity_report(self) -> IdentityReport:
        return IdentityReport(
            event_counts=tuple(
                sorted(Counter(event.event_type for event in self._audits).items())
            ),
            reason_counts=tuple(
                sorted(Counter(event.reason for event in self._audits).items())
            ),
            user_count=len(self._users),
            session_count=len(self._sessions),
        )

    def exportable_identity_views(self) -> tuple[IdentityExportRecord, ...]:
        return tuple(
            IdentityExportRecord(
                user_id=user.id,
                status=user.status,
                roles=tuple(sorted(self.active_roles(user.id))),
                links=tuple(
                    IdentityExportLink(
                        link.provider, link.provider_issuer, link.provider_subject
                    )
                    for link in sorted(
                        (
                            link
                            for link in self._links.values()
                            if link.product_user_id == user.id
                        ),
                        key=lambda link: (link.provider, link.provider_subject),
                    )
                ),
            )
            for user in sorted(self._users.values(), key=lambda user: str(user.id))
        )

    def exportable_identities(
        self,
    ) -> tuple[tuple[ProductUser, tuple[ExternalIdentityLink, ...]], ...]:
        users = sorted(self._users.values(), key=lambda item: str(item.id))
        return tuple(
            (
                user,
                tuple(
                    link
                    for link in self._links.values()
                    if link.product_user_id == user.id
                ),
            )
            for user in users
        )

    def session_count(self) -> int:
        return len(self._sessions)

    def purge_requests_before(self, cutoff: datetime) -> int:
        expired = [
            key for key, item in self._requests.items() if item.purge_after <= cutoff
        ]
        for key in expired:
            del self._requests[key]
        return len(expired)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Provide rollback semantics for local identity composition tests."""

        with self._lock:
            invitations = deepcopy(self._invitations)
            users = deepcopy(self._users)
            links = deepcopy(self._links)
            roles = deepcopy(self._roles)
            requests = deepcopy(self._requests)
            attempts = deepcopy(self._attempts)
            sessions = deepcopy(self._sessions)
            audits = deepcopy(self._audits)
            provider_events = deepcopy(self._provider_events)
            try:
                yield
            except Exception:
                self._invitations = invitations
                self._users = users
                self._links = links
                self._roles = roles
                self._requests = requests
                self._attempts = attempts
                self._sessions = sessions
                self._audits = audits
                self._provider_events = provider_events
                raise


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
        origin_count = self._count_recent(
            "origin_fingerprint", origin_fingerprint, window
        )
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
        return self.session.scalar(
            select(ProductUserRow).where(
                ProductUserRow.normalized_email == normalized_email
            )
        )

    def current_roles(self, user_id: UUID) -> set[str]:
        rows = self.session.scalars(
            select(RoleAssignmentRow.role).where(
                RoleAssignmentRow.product_user_id == user_id,
                RoleAssignmentRow.revoked_at.is_(None),
            )
        )
        return set(rows)

    def session_by_digest(self, token_digest: bytes) -> ProductSessionRow | None:
        return self.session.scalar(
            select(ProductSessionRow).where(
                ProductSessionRow.token_digest == token_digest
            )
        )

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
