from __future__ import annotations

# ruff: noqa: E501
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from tests.support.identity import access_with_recording_jobs, requested_attempt
from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.administration import AccessAdministration
from umbral.application.identity.authorization import AccessControl
from umbral.application.identity.contracts import IdentityError
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider


def _login() -> tuple[
    IdentityAccess, AccessControl, InMemoryIdentityStore, str, datetime
]:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store = InMemoryIdentityStore()
    admin = AccessAdministration(store)
    admin.preload_invitation("person@example.com")
    email = RecordingEmailAdapter()
    access = access_with_recording_jobs(store, FakeIdentityProvider(), email)
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="o",
        correlation_id=uuid4(),
        now=now,
    )
    attempt = requested_attempt(access, store)
    access.issue_attempt(attempt.id, now=now)
    token_hash = str(email.messages[0]["capture_url"]).split("token_hash=", 1)[1]
    session = access.confirm_magic_link(
        attempt_id=attempt.id, token_hash=str(token_hash), now=now
    )
    return access, AccessControl(store), store, session.token, now


def test_role_and_ownership_are_rechecked_on_each_operation() -> None:
    _, control, store, token, now = _login()
    user = store.user_for_email("person@example.com")
    assert user is not None
    user_id = user.id
    assert (
        control.authorize(
            token, action="product.resource.read", resource_owner_id=user_id, now=now
        ).user_id
        == user_id
    )
    with pytest.raises(IdentityError) as error:
        control.authorize(
            token, action="product.resource.read", resource_owner_id=uuid4(), now=now
        )
    assert error.value.code == "auth.access_denied"
    AccessAdministration(store).set_user_status(
        user_id, status="disabled", now=now + timedelta(minutes=1)
    )
    with pytest.raises(IdentityError):
        control.authorize(
            token,
            action="auth.session.read",
            resource_owner_id=None,
            now=now + timedelta(minutes=2),
        )
