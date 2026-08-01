from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from tests.support.identity import access_with_recording_jobs, requested_attempt
from umbral.application.identity.administration import AccessAdministration
from umbral.application.identity.contracts import IdentityError
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider


def test_provider_failure_creates_no_session_or_user() -> None:
    store = InMemoryIdentityStore()
    AccessAdministration(store).preload_invitation("person@example.com")
    provider = FakeIdentityProvider()
    provider.fail_generation = True
    access = access_with_recording_jobs(store, provider, RecordingEmailAdapter())
    now = datetime.now(timezone.utc)
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=now,
    )
    attempt = requested_attempt(access, store)
    access.issue_attempt(attempt.id, now=now)
    assert store.user_for_email("person@example.com") is None
    assert attempt.state == "failed"


def test_email_failure_creates_no_access_grant() -> None:
    store = InMemoryIdentityStore()
    AccessAdministration(store).preload_invitation("person@example.com")
    email = RecordingEmailAdapter()
    email.fail_send = True
    access = access_with_recording_jobs(store, FakeIdentityProvider(), email)
    now = datetime.now(timezone.utc)
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=now,
    )
    attempt = requested_attempt(access, store)
    access.issue_attempt(attempt.id, now=now)
    assert attempt.state == "failed"
    assert store.user_for_email("person@example.com") is None


def test_identity_verification_failure_does_not_activate_user() -> None:
    store = InMemoryIdentityStore()
    AccessAdministration(store).preload_invitation("person@example.com")
    provider = FakeIdentityProvider()
    provider.fail_verification = True
    email = RecordingEmailAdapter()
    access = access_with_recording_jobs(store, provider, email)
    now = datetime.now(timezone.utc)
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=now,
    )
    attempt = requested_attempt(access, store)
    access.issue_attempt(attempt.id, now=now)
    token_hash = str(email.messages[0]["capture_url"]).split("token_hash=", 1)[1]
    with pytest.raises(IdentityError):
        access.confirm_magic_link(attempt_id=attempt.id, token_hash=token_hash, now=now)
    assert store.user_for_email("person@example.com") is None


def test_provider_sign_out_failure_prevents_any_local_identity_mutation() -> None:
    class FailingRevocationProvider(FakeIdentityProvider):
        def revoke_provider_session(self, handle: str) -> None:
            raise IdentityError(
                "auth.provider_unavailable", status=503, recovery="retry_later"
            )

    store = InMemoryIdentityStore()
    invitation = AccessAdministration(store).preload_invitation("person@example.com")
    provider = FailingRevocationProvider()
    email = RecordingEmailAdapter()
    access = access_with_recording_jobs(store, provider, email)
    now = datetime.now(timezone.utc)
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=now,
    )
    attempt = requested_attempt(access, store)
    access.issue_attempt(attempt.id, now=now)
    token_hash = str(email.messages[0]["capture_url"]).split("token_hash=", 1)[1]

    with pytest.raises(IdentityError) as error:
        access.confirm_magic_link(attempt_id=attempt.id, token_hash=token_hash, now=now)

    assert error.value.code == "auth.provider_unavailable"
    assert attempt.state == "issued"
    assert invitation.status == "active"
    assert store.user_for_email("person@example.com") is None
