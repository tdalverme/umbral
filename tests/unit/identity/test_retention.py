from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.retention import purge_request_fingerprints
from umbral.application.jobs.contracts import JobContext
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider
from umbral.workers.identity import IdentityRetentionHandler


def test_request_fingerprints_purge_after_24_hours() -> None:
    store = InMemoryIdentityStore()
    access = IdentityAccess(store, FakeIdentityProvider(), RecordingEmailAdapter())
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    access.request_magic_link(
        email="unknown@example.com",
        origin_fingerprint="o",
        correlation_id=uuid4(),
        now=now,
    )
    assert (
        purge_request_fingerprints(store, now=now + timedelta(hours=24, seconds=1))
        == 1
    )


def test_retention_handler_uses_internal_store_only() -> None:
    store = InMemoryIdentityStore()
    access = IdentityAccess(store, FakeIdentityProvider(), RecordingEmailAdapter())
    result = IdentityRetentionHandler(access).run(
        JobContext(uuid4(), 1, uuid4(), "test", "identity")
    )
    assert result == {"purged_requests": 0, "result": "processed"}
