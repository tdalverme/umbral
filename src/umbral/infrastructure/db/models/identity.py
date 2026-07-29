"""PostgreSQL mappings for the private-beta identity slice."""
# ruff: noqa: E501

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base, IdentityAuditMixin


class IdentityInvitation(IdentityAuditMixin, Base):
    __tablename__ = "identity_invitations"
    __table_args__ = (
        UniqueConstraint("normalized_email", name="uq_identity_invitations_email"),
        CheckConstraint("status IN ('active', 'accepted')", name="ck_identity_invitations_status"),
        CheckConstraint("(status = 'active' AND accepted_user_id IS NULL AND accepted_at IS NULL) OR (status = 'accepted' AND accepted_user_id IS NOT NULL AND accepted_at IS NOT NULL)", name="ck_identity_invitations_acceptance"),
        Index("ix_identity_invitations_active_email", "normalized_email", postgresql_where=text("status = 'active'")),
        Index("ix_identity_invitations_accepted_user", "accepted_user_id"),
    )
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalization_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    accepted_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("product_users.id", ondelete="RESTRICT"), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    preload_actor_kind: Mapped[str] = mapped_column(String(30), nullable=False, default="deployment")
    preload_actor_id: Mapped[str] = mapped_column(String(128), nullable=False, default="local")
    preload_source: Mapped[str] = mapped_column(String(128), nullable=False)


class ProductUser(IdentityAuditMixin, Base):
    __tablename__ = "product_users"
    __table_args__ = (
        UniqueConstraint("normalized_email", name="uq_product_users_email"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_product_users_status"),
        CheckConstraint("(status = 'disabled' AND disabled_reason IS NOT NULL) OR (status = 'active' AND disabled_reason IS NULL)", name="ck_product_users_disabled_reason"),
        Index("ix_product_users_active", "id", postgresql_where=text("status = 'active'")),
        Index("ix_product_users_status_actor", "status_changed_by_user_id"),
    )
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalization_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    disabled_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status_changed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("product_users.id", ondelete="RESTRICT"), nullable=True)
    status_change_source: Mapped[str] = mapped_column(String(128), nullable=False)


class ExternalIdentityLink(IdentityAuditMixin, Base):
    __tablename__ = "external_identity_links"
    __table_args__ = (
        UniqueConstraint("provider", "provider_issuer", "provider_subject", name="uq_external_identity_subject"),
        UniqueConstraint("product_user_id", "provider", "provider_issuer", name="uq_external_identity_user_provider"),
        Index("ix_external_identity_user", "product_user_id"),
    )
    product_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("product_users.id", ondelete="RESTRICT"), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_issuer: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    verified_normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalization_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RoleAssignment(IdentityAuditMixin, Base):
    __tablename__ = "role_assignments"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'operator', 'administrator')", name="ck_role_assignments_role"),
        CheckConstraint("(revoked_at IS NULL AND revoke_reason IS NULL) OR (revoked_at IS NOT NULL AND revoke_reason IS NOT NULL)", name="ck_role_assignments_revocation"),
        Index("ix_role_assignments_current", "product_user_id", "role", postgresql_where=text("revoked_at IS NULL")),
        Index("ix_role_assignments_admin", "role", "product_user_id", postgresql_where=text("role = 'administrator' AND revoked_at IS NULL")),
        Index("ix_role_assignments_granted_by", "granted_by_user_id"),
        Index("ix_role_assignments_revoked_by", "revoked_by_user_id"),
    )
    product_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("product_users.id", ondelete="RESTRICT"), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    granted_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("product_users.id", ondelete="RESTRICT"), nullable=True)
    grant_actor_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    grant_actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    grant_reason: Mapped[str] = mapped_column(String(100), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("product_users.id", ondelete="RESTRICT"), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)


class MagicLinkRequest(Base):
    __tablename__ = "magic_link_requests"
    __table_args__ = (
        CheckConstraint("length(email_fingerprint) = 32 AND length(origin_fingerprint) = 32", name="ck_magic_link_requests_fingerprint_length"),
        Index("ix_magic_link_requests_email_window", "email_fingerprint_version", "email_fingerprint", "requested_at"),
        Index("ix_magic_link_requests_origin_window", "origin_fingerprint_version", "origin_fingerprint", "requested_at"),
        Index("ix_magic_link_requests_purge", "purge_after"),
        Index("ix_magic_link_requests_correlation", "correlation_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    email_fingerprint_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    origin_fingerprint: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    origin_fingerprint_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class MagicLinkAttempt(IdentityAuditMixin, Base):
    __tablename__ = "magic_link_attempts"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_magic_link_attempt_request"),
        CheckConstraint("subject_kind IN ('invitation', 'product_user')", name="ck_magic_link_attempt_subject_kind"),
        CheckConstraint("state IN ('pending', 'issuing', 'issued', 'consumed', 'superseded', 'expired', 'failed')", name="ck_magic_link_attempt_state"),
        CheckConstraint("(subject_kind = 'invitation' AND invitation_id IS NOT NULL AND product_user_id IS NULL) OR (subject_kind = 'product_user' AND product_user_id IS NOT NULL AND invitation_id IS NULL)", name="ck_magic_link_attempt_subject"),
        Index("ix_magic_link_attempts_current_invitation", "invitation_id", postgresql_where=text("state = 'issued'")),
        Index("ix_magic_link_attempts_current_user", "product_user_id", postgresql_where=text("state = 'issued'")),
        Index("ix_magic_link_attempts_job_execution", "job_execution_id"),
        Index("ix_magic_link_attempts_superseded_by", "superseded_by_id"),
    )
    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("magic_link_requests.id", ondelete="RESTRICT"), nullable=False)
    subject_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    invitation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("identity_invitations.id", ondelete="RESTRICT"), nullable=True)
    product_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("product_users.id", ondelete="RESTRICT"), nullable=True)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    job_execution_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("job_executions.id", ondelete="RESTRICT"), nullable=True)
    issuing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("magic_link_attempts.id", ondelete="RESTRICT"), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ProductSession(IdentityAuditMixin, Base):
    __tablename__ = "product_sessions"
    __table_args__ = (
        UniqueConstraint("token_digest", name="uq_product_sessions_token_digest"),
        UniqueConstraint("magic_link_attempt_id", name="uq_product_sessions_attempt"),
        CheckConstraint("length(token_digest) = 32", name="ck_product_sessions_token_digest"),
        CheckConstraint("(revoked_at IS NULL AND revocation_reason IS NULL) OR (revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)", name="ck_product_sessions_revocation"),
        Index("ix_product_sessions_active_user", "product_user_id", "last_activity_at", postgresql_where=text("revoked_at IS NULL")),
    )
    product_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("product_users.id", ondelete="RESTRICT"), nullable=False)
    magic_link_attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("magic_link_attempts.id", ondelete="RESTRICT"), nullable=False)
    token_digest: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)


class AccessAuditEvent(Base):
    __tablename__ = "access_audit_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_access_audit_provider_event"),
        Index("ix_access_audit_correlation", "correlation_id", "occurred_at"),
        Index("ix_access_audit_event_time", "event_type", "occurred_at"),
        Index("ix_access_audit_actor", "actor_user_id", "occurred_at"),
        Index("ix_access_audit_subject", "subject_user_id", "occurred_at"),
        Index("ix_access_audit_attempt", "attempt_id", "occurred_at"),
        Index("ix_access_audit_session", "session_id", "occurred_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str | None] = mapped_column(String(100), nullable=True)
    policy_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    actor_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("product_users.id", ondelete="RESTRICT"), nullable=True)
    subject_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("product_users.id", ondelete="RESTRICT"), nullable=True)
    invitation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("identity_invitations.id", ondelete="RESTRICT"), nullable=True)
    request_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("magic_link_requests.id", ondelete="RESTRICT"), nullable=True)
    attempt_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("magic_link_attempts.id", ondelete="RESTRICT"), nullable=True)
    session_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("product_sessions.id", ondelete="RESTRICT"), nullable=True)
    role_assignment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("role_assignments.id", ondelete="RESTRICT"), nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_event_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
