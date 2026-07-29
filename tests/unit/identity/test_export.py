from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.administration import AccessAdministration
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider
from umbral.ops.identity import export_identity_snapshot


def test_identity_export_contains_only_stable_internal_references() -> None:
    store = InMemoryIdentityStore()
    AccessAdministration(store).preload_invitation("person@example.com")
    email = RecordingEmailAdapter()
    access = IdentityAccess(store, FakeIdentityProvider(), email)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=now,
    )
    attempt = next(iter(store.attempts.values()))
    access.issue_attempt(attempt.id, now=now)
    token_hash = str(email.messages[0]["capture_url"]).split("token_hash=", 1)[1]
    access.confirm_magic_link(
        attempt_id=attempt.id,
        token_hash=str(token_hash),
        now=now,
    )
    exported = export_identity_snapshot(store)
    assert exported and exported[0]["roles"] == ["user"]
    assert "normalized_email" not in str(exported)
    assert "token" not in str(exported).lower()
