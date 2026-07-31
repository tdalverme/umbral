"""Resend HTTP adapter; provider payloads stay behind the email port."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from datetime import datetime
from uuid import UUID

from umbral.application.identity.contracts import EmailAcceptance, IdentityError


class ResendEmailAdapter:
    provider = "resend"

    def __init__(
        self,
        *,
        api_key: str,
        webhook_secret: bytes,
        sender: Callable[..., Mapping[str, object]] | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("Resend API key is required")
        self._sender = sender
        self._webhook_secret = webhook_secret

    def send_magic_link(
        self,
        *,
        attempt_id: UUID,
        normalized_email: str,
        capture_url: str,
        expires_at: datetime,
        idempotency_key: str,
        now: datetime,
    ) -> EmailAcceptance:
        if self._sender is None:
            raise IdentityError("auth.provider_unavailable", status=503, recovery="retry_later")
        try:
            result = self._sender(
                to=normalized_email,
                idempotency_key=idempotency_key,
                tags={"attempt_id": str(attempt_id)},
                tracking=False,
                capture_url=capture_url,
                expires_at=expires_at,
            )
            return EmailAcceptance("resend", str(result["id"]), now)
        except Exception as exc:
            raise IdentityError("auth.provider_unavailable", status=503, recovery="retry_later") from exc

    def verify_webhook(
        self,
        *,
        raw_body: bytes,
        headers: Mapping[str, str],
        received_at: datetime,
    ) -> Mapping[str, str] | None:
        timestamp = headers.get("svix-timestamp", "")
        signature = headers.get("svix-signature", "")
        expected = hmac.new(self._webhook_secret, timestamp.encode() + b"." + raw_body, hashlib.sha256).hexdigest()
        if not timestamp or not hmac.compare_digest(expected, signature):
            raise IdentityError("auth.webhook_invalid", status=401, recovery="none")
        try:
            if abs(received_at.timestamp() - int(timestamp)) > 300:
                raise IdentityError("auth.webhook_invalid", status=401, recovery="none")
        except ValueError as exc:
            raise IdentityError("auth.webhook_invalid", status=401, recovery="none") from exc
        try:
            payload = json.loads(raw_body)
            return {key: str(payload[key]) for key in ("id", "type", "email_id") if key in payload}
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise IdentityError("auth.webhook_invalid", status=400, recovery="none") from exc

    def health(self) -> str:
        return "ready" if self._sender is not None else "unavailable"
