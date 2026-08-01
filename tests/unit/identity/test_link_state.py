# ruff: noqa: E501
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from tests.support.identity import access_with_recording_jobs, requested_attempt
from umbral.application.identity.administration import AccessAdministration
from umbral.domain.identity.models import MagicLinkAttempt
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider


def test_link_valid_until_strict_expiry_boundary() -> None:
    issued = datetime(2026, 1, 1, tzinfo=timezone.utc)
    attempt = MagicLinkAttempt(
        uuid4(),
        uuid4(),
        "invitation",
        uuid4(),
        None,
        state="issued",
        issued_at=issued,
        expires_at=issued + timedelta(minutes=15),
    )
    assert attempt.current_and_valid(issued + timedelta(minutes=14, seconds=59))
    assert not attempt.current_and_valid(issued + timedelta(minutes=15))


def test_late_completion_cannot_reinstate_an_older_link() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store = InMemoryIdentityStore()
    AccessAdministration(store).preload_invitation("person@example.com")
    access = access_with_recording_jobs(
        store, FakeIdentityProvider(), RecordingEmailAdapter()
    )
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="one",
        correlation_id=uuid4(),
        now=now,
    )
    first = requested_attempt(access, store)
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="two",
        correlation_id=uuid4(),
        now=now + timedelta(seconds=1),
    )
    second = requested_attempt(access, store)
    assert second.id != first.id
    access.issue_attempt(second.id, now=now + timedelta(seconds=1))
    access.issue_attempt(first.id, now=now + timedelta(seconds=2))
    assert second.state == "issued"
    assert first.state == "superseded"
