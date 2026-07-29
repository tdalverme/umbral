"""Private-beta identity and access schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_private_beta_identity"
down_revision = "0001_foundation_runtime"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _audit_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", _ts(), nullable=False),
        sa.Column("updated_at", _ts(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("actor_kind", sa.String(30), nullable=False, server_default="system"),
        sa.Column("actor_id", sa.String(128)),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "identity_invitations",
        *_audit_columns(),
        sa.Column("normalized_email", sa.String(320), nullable=False),
        sa.Column("email_normalization_version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("accepted_user_id", _uuid()),
        sa.Column("accepted_at", _ts()),
        sa.Column("preload_actor_kind", sa.String(30), nullable=False),
        sa.Column("preload_actor_id", sa.String(128), nullable=False),
        sa.Column("preload_source", sa.String(128), nullable=False),
        sa.UniqueConstraint("normalized_email", name="uq_identity_invitations_email"),
        sa.CheckConstraint("status IN ('active', 'accepted')", name="ck_identity_invitations_status"),
        sa.CheckConstraint("(status = 'active' AND accepted_user_id IS NULL AND accepted_at IS NULL) OR (status = 'accepted' AND accepted_user_id IS NOT NULL AND accepted_at IS NOT NULL)", name="ck_identity_invitations_acceptance"),
    )
    op.create_table(
        "product_users",
        *_audit_columns(),
        sa.Column("normalized_email", sa.String(320), nullable=False),
        sa.Column("email_normalization_version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("disabled_reason", sa.String(100)),
        sa.Column("status_changed_at", _ts(), nullable=False),
        sa.Column("status_changed_by_user_id", _uuid()),
        sa.Column("status_change_source", sa.String(128), nullable=False),
        sa.UniqueConstraint("normalized_email", name="uq_product_users_email"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_product_users_status"),
        sa.CheckConstraint("(status = 'disabled' AND disabled_reason IS NOT NULL) OR (status = 'active' AND disabled_reason IS NULL)", name="ck_product_users_disabled_reason"),
    )
    op.create_foreign_key("fk_identity_invitations_accepted_user", "identity_invitations", "product_users", ["accepted_user_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_product_users_status_actor", "product_users", "product_users", ["status_changed_by_user_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_identity_invitations_active_email", "identity_invitations", ["normalized_email"], postgresql_where=sa.text("status = 'active'"))
    op.create_index("ix_identity_invitations_accepted_user", "identity_invitations", ["accepted_user_id"])
    op.create_index("ix_product_users_active", "product_users", ["id"], postgresql_where=sa.text("status = 'active'"))
    op.create_index("ix_product_users_status_actor", "product_users", ["status_changed_by_user_id"])

    op.create_table(
        "external_identity_links",
        *_audit_columns(),
        sa.Column("product_user_id", _uuid(), sa.ForeignKey("product_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_issuer", sa.String(255), nullable=False),
        sa.Column("provider_subject", sa.String(255), nullable=False),
        sa.Column("verified_normalized_email", sa.String(320), nullable=False),
        sa.Column("email_normalization_version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("verified_at", _ts(), nullable=False),
        sa.Column("linked_at", _ts(), nullable=False),
        sa.UniqueConstraint("provider", "provider_issuer", "provider_subject", name="uq_external_identity_subject"),
        sa.UniqueConstraint("product_user_id", "provider", "provider_issuer", name="uq_external_identity_user_provider"),
    )
    op.create_index("ix_external_identity_user", "external_identity_links", ["product_user_id"])

    op.create_table(
        "role_assignments",
        *_audit_columns(),
        sa.Column("product_user_id", _uuid(), sa.ForeignKey("product_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("granted_at", _ts(), nullable=False),
        sa.Column("granted_by_user_id", _uuid(), sa.ForeignKey("product_users.id", ondelete="RESTRICT")),
        sa.Column("grant_actor_kind", sa.String(30), nullable=False),
        sa.Column("grant_actor_id", sa.String(128), nullable=False),
        sa.Column("grant_reason", sa.String(100), nullable=False),
        sa.Column("revoked_at", _ts()),
        sa.Column("revoked_by_user_id", _uuid(), sa.ForeignKey("product_users.id", ondelete="RESTRICT")),
        sa.Column("revoke_reason", sa.String(100)),
        sa.CheckConstraint("role IN ('user', 'operator', 'administrator')", name="ck_role_assignments_role"),
        sa.CheckConstraint("(revoked_at IS NULL AND revoke_reason IS NULL) OR (revoked_at IS NOT NULL AND revoke_reason IS NOT NULL)", name="ck_role_assignments_revocation"),
    )
    op.create_index("ix_role_assignments_current", "role_assignments", ["product_user_id", "role"], postgresql_where=sa.text("revoked_at IS NULL"))
    op.create_index("ix_role_assignments_admin", "role_assignments", ["role", "product_user_id"], postgresql_where=sa.text("role = 'administrator' AND revoked_at IS NULL"))
    op.create_index("ix_role_assignments_granted_by", "role_assignments", ["granted_by_user_id"])
    op.create_index("ix_role_assignments_revoked_by", "role_assignments", ["revoked_by_user_id"])

    op.create_table(
        "magic_link_requests",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("email_fingerprint", sa.LargeBinary(32), nullable=False),
        sa.Column("email_fingerprint_version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("origin_fingerprint", sa.LargeBinary(32), nullable=False),
        sa.Column("origin_fingerprint_version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("requested_at", _ts(), nullable=False),
        sa.Column("purge_after", _ts(), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
        sa.CheckConstraint("length(email_fingerprint) = 32 AND length(origin_fingerprint) = 32", name="ck_magic_link_requests_fingerprint_length"),
    )
    op.create_index("ix_magic_link_requests_email_window", "magic_link_requests", ["email_fingerprint_version", "email_fingerprint", "requested_at"])
    op.create_index("ix_magic_link_requests_origin_window", "magic_link_requests", ["origin_fingerprint_version", "origin_fingerprint", "requested_at"])
    op.create_index("ix_magic_link_requests_purge", "magic_link_requests", ["purge_after"])
    op.create_index("ix_magic_link_requests_correlation", "magic_link_requests", ["correlation_id"])

    op.create_table(
        "magic_link_attempts",
        *_audit_columns(),
        sa.Column("request_id", _uuid(), sa.ForeignKey("magic_link_requests.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("subject_kind", sa.String(30), nullable=False),
        sa.Column("invitation_id", _uuid(), sa.ForeignKey("identity_invitations.id", ondelete="RESTRICT")),
        sa.Column("product_user_id", _uuid(), sa.ForeignKey("product_users.id", ondelete="RESTRICT")),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("job_execution_id", _uuid(), sa.ForeignKey("job_executions.id", ondelete="RESTRICT")),
        sa.Column("issuing_started_at", _ts()),
        sa.Column("provider_generated_at", _ts()),
        sa.Column("issued_at", _ts()),
        sa.Column("expires_at", _ts()),
        sa.Column("consumed_at", _ts()),
        sa.Column("superseded_at", _ts()),
        sa.Column("superseded_by_id", _uuid(), sa.ForeignKey("magic_link_attempts.id", ondelete="RESTRICT")),
        sa.Column("provider_message_id", sa.String(200)),
        sa.Column("failure_reason", sa.String(100)),
        sa.UniqueConstraint("request_id", name="uq_magic_link_attempt_request"),
        sa.CheckConstraint("subject_kind IN ('invitation', 'product_user')", name="ck_magic_link_attempt_subject_kind"),
        sa.CheckConstraint("state IN ('pending', 'issuing', 'issued', 'consumed', 'superseded', 'expired', 'failed')", name="ck_magic_link_attempt_state"),
        sa.CheckConstraint("(subject_kind = 'invitation' AND invitation_id IS NOT NULL AND product_user_id IS NULL) OR (subject_kind = 'product_user' AND product_user_id IS NOT NULL AND invitation_id IS NULL)", name="ck_magic_link_attempt_subject"),
    )
    op.create_index("ix_magic_link_attempts_current_invitation", "magic_link_attempts", ["invitation_id"], postgresql_where=sa.text("state = 'issued'"))
    op.create_index("ix_magic_link_attempts_current_user", "magic_link_attempts", ["product_user_id"], postgresql_where=sa.text("state = 'issued'"))
    op.create_index("ix_magic_link_attempts_job_execution", "magic_link_attempts", ["job_execution_id"])
    op.create_index("ix_magic_link_attempts_superseded_by", "magic_link_attempts", ["superseded_by_id"])

    op.create_table(
        "product_sessions",
        *_audit_columns(),
        sa.Column("product_user_id", _uuid(), sa.ForeignKey("product_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("magic_link_attempt_id", _uuid(), sa.ForeignKey("magic_link_attempts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("token_digest", sa.LargeBinary(32), nullable=False),
        sa.Column("last_activity_at", _ts(), nullable=False),
        sa.Column("revoked_at", _ts()),
        sa.Column("revocation_reason", sa.String(50)),
        sa.UniqueConstraint("token_digest", name="uq_product_sessions_token_digest"),
        sa.UniqueConstraint("magic_link_attempt_id", name="uq_product_sessions_attempt"),
        sa.CheckConstraint("length(token_digest) = 32", name="ck_product_sessions_token_digest"),
        sa.CheckConstraint("(revoked_at IS NULL AND revocation_reason IS NULL) OR (revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)", name="ck_product_sessions_revocation"),
    )
    op.create_index("ix_product_sessions_active_user", "product_sessions", ["product_user_id", "last_activity_at"], postgresql_where=sa.text("revoked_at IS NULL"))

    op.create_table(
        "access_audit_events",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100)),
        sa.Column("policy_version", sa.String(100)),
        sa.Column("actor_kind", sa.String(30), nullable=False),
        sa.Column("actor_user_id", _uuid(), sa.ForeignKey("product_users.id", ondelete="RESTRICT")),
        sa.Column("subject_user_id", _uuid(), sa.ForeignKey("product_users.id", ondelete="RESTRICT")),
        sa.Column("invitation_id", _uuid(), sa.ForeignKey("identity_invitations.id", ondelete="RESTRICT")),
        sa.Column("request_id", _uuid(), sa.ForeignKey("magic_link_requests.id", ondelete="RESTRICT")),
        sa.Column("attempt_id", _uuid(), sa.ForeignKey("magic_link_attempts.id", ondelete="RESTRICT")),
        sa.Column("session_id", _uuid(), sa.ForeignKey("product_sessions.id", ondelete="RESTRICT")),
        sa.Column("role_assignment_id", _uuid(), sa.ForeignKey("role_assignments.id", ondelete="RESTRICT")),
        sa.Column("resource_type", sa.String(100)),
        sa.Column("resource_id", _uuid()),
        sa.Column("provider", sa.String(50)),
        sa.Column("provider_event_id", sa.String(200)),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
        sa.Column("occurred_at", _ts(), nullable=False),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_access_audit_provider_event"),
    )
    op.create_index("ix_access_audit_correlation", "access_audit_events", ["correlation_id", "occurred_at"])
    op.create_index("ix_access_audit_event_time", "access_audit_events", ["event_type", "occurred_at"])
    op.create_index("ix_access_audit_actor", "access_audit_events", ["actor_user_id", "occurred_at"])
    op.create_index("ix_access_audit_subject", "access_audit_events", ["subject_user_id", "occurred_at"])
    op.create_index("ix_access_audit_attempt", "access_audit_events", ["attempt_id", "occurred_at"])
    op.create_index("ix_access_audit_session", "access_audit_events", ["session_id", "occurred_at"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = ("access_audit_events", "product_sessions", "magic_link_attempts", "magic_link_requests", "role_assignments", "external_identity_links", "identity_invitations", "product_users")
    for table in tables:
        if bind.dialect.name == "postgresql" and bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError("identity downgrade requires empty tables")
    for table in tables:
        op.drop_table(table)
