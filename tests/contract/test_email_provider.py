from __future__ import annotations

# ruff: noqa: E501
from datetime import datetime, timezone
from uuid import uuid4

from umbral.infrastructure.email.recording import RecordingEmailAdapter


def test_email_idempotency_and_tracking_disabled() -> None:
    adapter = RecordingEmailAdapter()
    now = datetime.now(timezone.utc)
    first = adapter.send_magic_link(attempt_id=uuid4(), normalized_email="p@example.com", capture_url="http://localhost:3000/auth/capture", expires_at=now, idempotency_key="identity.magic-link/a", now=now)
    second = adapter.send_magic_link(attempt_id=uuid4(), normalized_email="p@example.com", capture_url="http://localhost:3000/auth/capture", expires_at=now, idempotency_key="identity.magic-link/a", now=now)
    assert first.message_id == second.message_id
    assert adapter.messages[0]["tracking"] is False
