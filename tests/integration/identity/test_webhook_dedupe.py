from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

import pytest

from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.contracts import IdentityError
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider


def test_webhook_is_verified_and_deduplicated() -> None:
    email = RecordingEmailAdapter(webhook_secret=b"secret")
    access = IdentityAccess(InMemoryIdentityStore(), FakeIdentityProvider(), email)
    body = json.dumps({"id": "evt-1", "type": "email.delivered"}).encode()
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    signature = hmac.new(
        b"secret", timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    headers = {"svix-timestamp": timestamp, "svix-signature": signature}
    assert access.process_email_webhook(
        raw_body=body, headers=headers, now=datetime.now(timezone.utc)
    )
    assert not access.process_email_webhook(
        raw_body=body, headers=headers, now=datetime.now(timezone.utc)
    )


def test_webhook_rejects_tampering_and_stale_signatures() -> None:
    email = RecordingEmailAdapter(webhook_secret=b"secret")
    access = IdentityAccess(InMemoryIdentityStore(), FakeIdentityProvider(), email)
    body = b'{"id":"evt-2","type":"email.delivered"}'
    now = datetime.now(timezone.utc)
    stale_timestamp = str(int(now.timestamp()) - 301)
    stale_signature = hmac.new(
        b"secret", stale_timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    with pytest.raises(IdentityError):
        access.process_email_webhook(
            raw_body=body,
            headers={
                "svix-timestamp": stale_timestamp,
                "svix-signature": stale_signature,
            },
            now=now,
        )
    with pytest.raises(IdentityError):
        access.process_email_webhook(
            raw_body=body,
            headers={
                "svix-timestamp": str(int(now.timestamp())),
                "svix-signature": "tampered",
            },
            now=now,
        )


def test_unknown_webhook_is_ignored_without_access_mutation() -> None:
    email = RecordingEmailAdapter(webhook_secret=b"secret")
    access = IdentityAccess(InMemoryIdentityStore(), FakeIdentityProvider(), email)
    body = b'{"id":"evt-3","type":"email.unknown"}'
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))
    signature = hmac.new(
        b"secret", timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    assert access.process_email_webhook(
        raw_body=body,
        headers={"svix-timestamp": timestamp, "svix-signature": signature},
        now=datetime.now(timezone.utc),
    )
    assert access.store.audit_events() == ()
