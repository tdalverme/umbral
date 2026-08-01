 # ruff: noqa: E501
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.administration import AccessAdministration
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider


def _service() -> tuple[IdentityAccess, InMemoryIdentityStore]:
    store = InMemoryIdentityStore()
    AccessAdministration(store).preload_invitation("person@example.com")
    return IdentityAccess(store, FakeIdentityProvider(), RecordingEmailAdapter()), store


def test_email_limit_is_exact_and_does_not_create_attempt() -> None:
    service, store = _service()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for _ in range(3):
        service.request_magic_link(email="person@example.com", origin_fingerprint="same", correlation_id=uuid4(), now=now)
    third = store.latest_attempt()
    assert third is not None
    service.request_magic_link(email="person@example.com", origin_fingerprint="same", correlation_id=uuid4(), now=now)
    assert store.latest_attempt() == third
    service.request_magic_link(email="person@example.com", origin_fingerprint="same", correlation_id=uuid4(), now=now + timedelta(minutes=15, seconds=1))
    assert store.latest_attempt() != third
 # ruff: noqa: E501
