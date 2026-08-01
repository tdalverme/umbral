from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

import pytest
import resend

from umbral.application.identity.contracts import IdentityError
from umbral.infrastructure.email.resend import ResendEmailAdapter

WEBHOOK_SECRET = "whsec_dGVzdC13ZWJob29rLXNlY3JldA=="
WEBHOOK_KEY = b"test-webhook-secret"


def _signed_headers(
    raw_body: bytes, *, event_id: str, timestamp: int
) -> dict[str, str]:
    signed_content = b".".join((event_id.encode(), str(timestamp).encode(), raw_body))
    signature = base64.b64encode(
        hmac.new(WEBHOOK_KEY, signed_content, hashlib.sha256).digest()
    ).decode()
    return {
        "svix-id": event_id,
        "svix-timestamp": str(timestamp),
        "svix-signature": f"v1,{signature}",
    }


def test_resend_webhook_verifies_the_raw_svix_envelope_and_maps_closed_fields() -> None:
    observed: list[Mapping[str, object]] = []
    now = datetime.now(timezone.utc)
    raw_body = (
        b'{\n  "id": "evt-1", "type": "email.delivered", '
        b'"data": {"email_id": "email-1", "extra": "ignored"}\n}'
    )
    headers = _signed_headers(
        raw_body, event_id="msg_evt_1", timestamp=int(now.timestamp())
    )

    def verifier(options: Mapping[str, object]) -> object:
        observed.append(options)
        return resend.Webhooks.verify(options)  # type: ignore[arg-type]

    adapter = ResendEmailAdapter(
        sender_email="Umbral <onboarding@resend.dev>",
        webhook_secret=WEBHOOK_SECRET,
        verifier=verifier,
    )

    event = adapter.verify_webhook(
        raw_body=raw_body,
        headers=headers,
        received_at=now,
    )

    assert event == {"id": "evt-1", "type": "email.delivered", "email_id": "email-1"}
    assert observed == [
        {
            "payload": raw_body.decode(),
            "headers": {
                "id": "msg_evt_1",
                "timestamp": str(int(now.timestamp())),
                "signature": headers["svix-signature"],
            },
            "webhook_secret": WEBHOOK_SECRET,
        }
    ]


@pytest.mark.parametrize(
    "raw_body,headers",
    [
        (
            b'{"id":"evt-2","type":"email.delivered","data":{"email_id":"email-2"}}',
            _signed_headers(
                b'{"id":"evt-2","type":"email.delivered","data":{"email_id":"email-2"}}',
                event_id="msg_evt_2",
                timestamp=int(
                    (datetime.now(timezone.utc) - timedelta(minutes=6)).timestamp()
                ),
            ),
        ),
        (
            b'{"id":"evt-3","type":"email.delivered","data":{"email_id":"email-3"}}',
            _signed_headers(
                b'{"id":"evt-3","type":"email.delivered","data":{"email_id":"email-3"}}',
                event_id="msg_evt_3",
                timestamp=int(datetime.now(timezone.utc).timestamp()),
            )
            | {"svix-signature": "v1,tampered"},
        ),
        (
            b'{"id":',
            _signed_headers(
                b'{"id":',
                event_id="msg_evt_4",
                timestamp=int(datetime.now(timezone.utc).timestamp()),
            ),
        ),
        (
            b'{"id":"evt-5"}',
            {"svix-timestamp": str(int(datetime.now(timezone.utc).timestamp()))},
        ),
    ],
)
def test_resend_webhook_rejects_stale_tampered_malformed_and_incomplete_envelopes(
    raw_body: bytes, headers: Mapping[str, str]
) -> None:
    adapter = ResendEmailAdapter(
        sender_email="Umbral <onboarding@resend.dev>",
        webhook_secret=WEBHOOK_SECRET,
        verifier=lambda options: resend.Webhooks.verify(options),  # type: ignore[arg-type]
    )

    with pytest.raises(IdentityError):
        adapter.verify_webhook(
            raw_body=raw_body,
            headers=headers,
            received_at=datetime.now(timezone.utc),
        )
