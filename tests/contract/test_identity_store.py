"""Behavioral conformance for the identity persistence seam."""
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import replace
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


def test_store_finds_current_attempt_and_applies_exact_rate_window(
    store: InMemoryIdentityStore,
) -> None:
    """Catches stores that return stale attempts or include the 15-minute boundary."""

    user = ProductUser(uuid4(), "rate@example.com", created_at=NOW, status_changed_at=NOW)
    current_request = MagicLinkRequest(uuid4(), b"e" * 32, b"o" * 32, "eligible", NOW, NOW + timedelta(hours=24), uuid4())
    current = MagicLinkAttempt(uuid4(), current_request.id, "product_user", None, user.id, state="issued", issued_at=NOW, expires_at=NOW + timedelta(minutes=15))
    newer_request = MagicLinkRequest(uuid4(), b"e" * 32, b"n" * 32, "eligible", NOW + timedelta(seconds=1), NOW + timedelta(hours=24), uuid4())
    newer = MagicLinkAttempt(uuid4(), newer_request.id, "product_user", None, user.id, state="issued", issued_at=NOW + timedelta(seconds=1), expires_at=NOW + timedelta(minutes=15))
    boundary_request = MagicLinkRequest(uuid4(), b"e" * 32, b"x" * 32, "eligible", NOW - timedelta(minutes=15), NOW, uuid4())
    recent_request = MagicLinkRequest(uuid4(), b"e" * 32, b"y" * 32, "eligible", NOW - timedelta(minutes=14, seconds=59), NOW, uuid4())

    with store.transaction():
        store.save_user(user)
        store.save_request(current_request)
        store.save_attempt(current)
        store.save_request(newer_request)
        store.save_attempt(newer)
        store.save_request(boundary_request)
        store.save_request(recent_request)

    assert store.current_attempt(product_user_id=user.id) == newer
    assert store.current_attempt(invitation_id=uuid4()) is None
    assert store.recent_requests(b"e" * 32, now=NOW, field="email_fingerprint") == 3


def test_store_persists_reloaded_transitions_for_every_mutable_record(
    store: InMemoryIdentityStore,
) -> None:
    """Catches adapters that save only creations or retain stale record versions."""

    invitation = Invitation.new("transition@example.com")
    user = ProductUser(uuid4(), "transition@example.com", created_at=NOW, status_changed_at=NOW)
    link = ExternalIdentityLink(uuid4(), user.id, "provider", "issuer", "subject-transition", user.normalized_email, NOW)
    role = RoleAssignment(uuid4(), user.id, "user", NOW)
    request = MagicLinkRequest(uuid4(), b"r" * 32, b"o" * 32, "eligible", NOW, NOW + timedelta(hours=24), uuid4())
    attempt = MagicLinkAttempt(uuid4(), request.id, "product_user", None, user.id)
    session = ProductSession(uuid4(), user.id, attempt.id, b"s" * 32, NOW)
    with store.transaction():
        store.save_invitation(invitation)
        store.save_user(user)
        store.save_link(link)
        store.save_role(role)
        store.save_request(request)
        store.save_attempt(attempt)
        store.save_session(session)
        invitation = replace(invitation, status="accepted", accepted_user_id=user.id, accepted_at=NOW)
        user = replace(user, status="disabled", disabled_reason="review", status_changed_at=NOW)
        link = replace(link, verified_normalized_email="new@example.com")
        role = replace(role, revoked_at=NOW)
        request = replace(request, decision="email_limited")
        attempt = replace(attempt, state="failed", failure_reason="job_submission_failed")
        session = replace(session, revoked_at=NOW, revocation_reason="logout")
        store.save_invitation(invitation)
        store.save_user(user)
        store.save_link(link)
        store.save_role(role)
        store.save_request(request)
        store.save_attempt(attempt)
        store.save_session(session)

    assert store.invitation_for_email(invitation.normalized_email) == invitation
    assert store.user(user.id) == user
    assert store.link_for_subject("provider", "issuer", "subject-transition") == link
    assert store.active_role(user.id, "user") is None
    assert store.request(request.id) == request
    assert store.attempt(attempt.id) == attempt
    assert store.session_by_digest(b"s" * 32) == session


def test_store_rolls_back_provider_dedupe_deeply_and_reentrantly(
    store: InMemoryIdentityStore,
) -> None:
    """Catches inner rollback corruption of state or a permanently claimed event."""

    invitation = Invitation.new("nested@example.com")
    event = AccessAuditEvent(uuid4(), "magic_link.delivery_observed.v1", "observed", "email_delivered", uuid4(), NOW, provider="email", provider_event_id="evt-nested")

    with store.transaction():
        store.save_invitation(invitation)
        with pytest.raises(RuntimeError, match="inner"):
            with store.transaction():
                invitation.status = "accepted"
                store.save_invitation(invitation)
                store.append_provider_audit_once("email", "evt-nested", event)
                raise RuntimeError("inner")
        assert store.invitation_for_email("nested@example.com") is not None
        assert store.invitation_for_email("nested@example.com").status == "active"
        assert store.append_provider_audit_once("email", "evt-nested", event) is True

    assert store.audit_events() == (event,)
