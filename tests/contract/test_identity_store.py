"""Behavioral conformance for the identity persistence seam."""
# ruff: noqa: E501

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

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
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture(params=[InMemoryIdentityStore])
def store(request: pytest.FixtureRequest) -> InMemoryIdentityStore:
    return request.param()


def test_store_persists_identity_records_through_its_behavioral_interface(
    store: InMemoryIdentityStore,
) -> None:
    """Catches replacing persistence operations with mutable collection access."""

    invitation = Invitation.new("person@example.com")
    user = ProductUser(
        uuid4(), "person@example.com", created_at=NOW, status_changed_at=NOW
    )
    link = ExternalIdentityLink(
        uuid4(), user.id, "provider", "issuer", "subject", user.normalized_email, NOW
    )
    role = RoleAssignment(uuid4(), user.id, "user", NOW)
    request = MagicLinkRequest(
        uuid4(),
        b"e" * 32,
        b"o" * 32,
        "eligible",
        NOW,
        NOW + timedelta(hours=24),
        uuid4(),
    )
    attempt = MagicLinkAttempt(
        uuid4(),
        request.id,
        "product_user",
        None,
        user.id,
        state="issued",
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
        provider_message_id="message-1",
    )
    session = ProductSession(uuid4(), user.id, attempt.id, b"d" * 32, NOW)

    with store.transaction():
        store.save_invitation(invitation)
        store.save_user(user)
        store.save_link(link)
        store.save_role(role)
        store.save_request(request)
        store.save_attempt(attempt)
        store.save_session(session)

    assert store.invitation_for_email("person@example.com") == invitation
    assert store.user(user.id) == user
    assert store.user_for_email("person@example.com") == user
    assert store.link_for_subject("provider", "issuer", "subject") == link
    assert store.active_roles(user.id) == {"user"}
    assert store.active_role(user.id, "user") == role
    assert store.request(request.id) == request
    assert store.attempt(attempt.id) == attempt
    assert store.attempt_for_provider_message("message-1") == attempt
    assert store.session_by_digest(b"d" * 32) == session


def test_store_deduplicates_provider_event_and_audit_together(
    store: InMemoryIdentityStore,
) -> None:
    """Catches a duplicate webhook adding audit rows or a split claim/audit write."""

    event = AccessAuditEvent(
        uuid4(),
        "magic_link.delivery_observed.v1",
        "observed",
        "email_delivered",
        uuid4(),
        NOW,
        provider="email",
        provider_event_id="evt-1",
    )

    with store.transaction():
        first = store.append_provider_audit_once("email", "evt-1", event)
    with store.transaction():
        second = store.append_provider_audit_once("email", "evt-1", event)

    assert first is True
    assert second is False
    assert store.audit_events() == (event,)


def test_store_rolls_back_state_and_audit_together(
    store: InMemoryIdentityStore,
) -> None:
    """Catches transactions that retain one side of a state-plus-audit change."""

    invitation = Invitation.new("rollback@example.com")
    event = AccessAuditEvent(
        uuid4(),
        "invitation.preloaded.v1",
        "accepted",
        "eligible",
        uuid4(),
        NOW,
        invitation_id=invitation.id,
    )

    with pytest.raises(RuntimeError, match="rollback"):
        with store.transaction():
            store.save_invitation(invitation)
            store.append_audit(event)
            raise RuntimeError("rollback")

    assert store.invitation_for_email("rollback@example.com") is None
    assert store.audit_events() == ()
