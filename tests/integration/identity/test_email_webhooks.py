from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone

import pytest

from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.contracts import IdentityError
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider


def test_raw_body_signature_rejects_tampered_delivery() -> None:
    now = datetime.now(timezone.utc)
    body = b'{"id":"evt","type":"email.delivered"}'
    timestamp = str(int(now.timestamp()))
    signature = hmac.new(
        b"secret", timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    access = IdentityAccess(
        InMemoryIdentityStore(),
        FakeIdentityProvider(),
        RecordingEmailAdapter(webhook_secret=b"secret"),
    )
    with pytest.raises(IdentityError):
        access.process_email_webhook(
            raw_body=body + b"x",
            headers={
                "svix-timestamp": timestamp,
                "svix-signature": signature,
            },
            now=now,
        )
