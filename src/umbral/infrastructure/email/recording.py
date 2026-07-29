"""Recording/Mailpit-compatible email adapter with no tracking."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from umbral.application.identity.contracts import EmailAcceptance, IdentityError


class RecordingEmailAdapter:
    provider = "recording"

    def __init__(self, *, webhook_secret: bytes | None = None) -> None:
        self.webhook_secret = webhook_secret or secrets.token_bytes(32)
        self.messages: list[dict[str, object]] = []
        self.fail_send = False

    def send_magic_link(self, *, attempt_id: UUID, normalized_email: str, capture_url: str, expires_at: datetime, idempotency_key: str, now: datetime) -> EmailAcceptance:
        if self.fail_send:
            raise IdentityError("auth.provider_unavailable", status=503, recovery="retry_later")
        if any(message["idempotency_key"] == idempotency_key for message in self.messages):
            existing = next(message for message in self.messages if message["idempotency_key"] == idempotency_key)
            return EmailAcceptance(self.provider, str(existing["message_id"]), now)
        message_id = f"mail-{len(self.messages) + 1}"
        self.messages.append({
            "attempt_id": attempt_id,
            "idempotency_key": idempotency_key,
            "message_id": message_id,
            "to": normalized_email,
            "capture_url": capture_url,
            "expires_at": expires_at,
            "tracking": False,
        })
        return EmailAcceptance(self.provider, message_id, now)

    def verify_webhook(self, *, raw_body: bytes, headers: Mapping[str, str], received_at: datetime) -> Mapping[str, str] | None:
        timestamp = headers.get("svix-timestamp", "")
        signature = headers.get("svix-signature", "")
        if not timestamp or not signature:
            raise IdentityError("auth.webhook_invalid", status=401, recovery="none")
        try:
            if abs(received_at.timestamp() - int(timestamp)) > 300:
                raise IdentityError("auth.webhook_invalid", status=401, recovery="none")
        except ValueError as exc:
            raise IdentityError("auth.webhook_invalid", status=401, recovery="none") from exc
        expected = hmac.new(self.webhook_secret, timestamp.encode() + b"." + raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise IdentityError("auth.webhook_invalid", status=401, recovery="none")
        try:
            data = json.loads(raw_body)
            if not isinstance(data, dict):
                raise ValueError
            return {key: str(data[key]) for key in ("id", "type", "email_id") if key in data}
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise IdentityError("auth.webhook_invalid", status=400, recovery="none") from exc
