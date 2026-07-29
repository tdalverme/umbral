 # ruff: noqa: E501
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.administration import AccessAdministration
from umbral.application.identity.authorization import AccessControl
from umbral.application.identity.contracts import IdentityError
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider


def test_activation_is_one_user_and_latest_link_wins() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store = InMemoryIdentityStore()
    AccessAdministration(store).preload_invitation("person@example.com")
    provider = FakeIdentityProvider()
    email = RecordingEmailAdapter()
    service = IdentityAccess(store, provider, email)
    service.request_magic_link(email="person@example.com", origin_fingerprint="a", correlation_id=uuid4(), now=now)
    first = next(iter(store.attempts.values()))
    service.issue_attempt(first.id, now=now)
    service.request_magic_link(email="person@example.com", origin_fingerprint="b", correlation_id=uuid4(), now=now + timedelta(seconds=1))
    second = next(item for item in store.attempts.values() if item.id != first.id)
    service.issue_attempt(second.id, now=now + timedelta(seconds=1))
    assert first.state == "superseded"
    token_hash = str(email.messages[-1]["capture_url"]).split("token_hash=", 1)[1]
    session = service.confirm_magic_link(attempt_id=second.id, token_hash=str(token_hash), now=now + timedelta(seconds=2))
    assert len(store.users) == 1
    assert len(store.links) == 1
    assert len(store.sessions) == 1
    with pytest.raises(IdentityError) as error:
        service.confirm_magic_link(attempt_id=second.id, token_hash=str(token_hash), now=now + timedelta(seconds=3))
    assert error.value.code == "auth.link_unavailable"
    AccessControl(store).authorize(session.token, action="auth.session.read", resource_owner_id=None, now=now + timedelta(days=6, hours=23))
    with pytest.raises(IdentityError) as error:
        AccessControl(store).authorize(session.token, action="auth.session.read", resource_owner_id=None, now=now + timedelta(days=13, hours=23))
    assert error.value.status == 401


def test_repeat_magic_link_reuses_same_product_identity() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store = InMemoryIdentityStore()
    AccessAdministration(store).preload_invitation("person@example.com")
    provider = FakeIdentityProvider()
    email = RecordingEmailAdapter()
    service = IdentityAccess(store, provider, email)

    service.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=now,
    )
    first = next(iter(store.attempts.values()))
    service.issue_attempt(first.id, now=now)
    first_token = str(email.messages[-1]["capture_url"]).split("token_hash=", 1)[1]
    first_session = service.confirm_magic_link(
        attempt_id=first.id, token_hash=str(first_token), now=now
    )

    service.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=now + timedelta(minutes=1),
    )
    second = next(item for item in store.attempts.values() if item.id != first.id)
    service.issue_attempt(second.id, now=now + timedelta(minutes=1))
    second_token = str(email.messages[-1]["capture_url"]).split("token_hash=", 1)[1]
    second_session = service.confirm_magic_link(
        attempt_id=second.id,
        token_hash=str(second_token),
        now=now + timedelta(minutes=1),
    )

    assert second_session.user_id == first_session.user_id
    assert len(store.users) == 1
    assert len(store.links) == 1
