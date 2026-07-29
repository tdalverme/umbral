from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from umbral.infrastructure.email.resend import ResendEmailAdapter


def test_resend_adapter_disables_tracking_and_keeps_idempotency() -> None:
    calls: list[dict[str, object]] = []

    def sender(**payload: object) -> dict[str, object]:
        calls.append(payload)
        return {"id": "msg-1"}

    adapter = ResendEmailAdapter(api_key="key", webhook_secret=b"secret", sender=sender)
    adapter.send_magic_link(
        attempt_id=uuid4(),
        normalized_email="person@example.com",
        capture_url="http://localhost:3000/auth/capture",
        expires_at=datetime.now(timezone.utc),
        idempotency_key="identity.magic-link/1",
        now=datetime.now(timezone.utc),
    )
    assert calls[0]["tracking"] is False
    assert calls[0]["idempotency_key"] == "identity.magic-link/1"
