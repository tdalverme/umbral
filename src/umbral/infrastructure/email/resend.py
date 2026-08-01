"""Resend HTTP adapter; provider payloads stay behind the email port."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import cast
from uuid import UUID

from umbral.application.identity.contracts import EmailAcceptance, IdentityError


class ResendEmailAdapter:
    provider = "resend"

    def __init__(
        self,
        *,
        sender_email: str,
        webhook_secret: str,
        sender: Callable[
            [Mapping[str, object], Mapping[str, str]], Mapping[str, object]
        ]
        | None = None,
        verifier: Callable[[Mapping[str, object]], object] | None = None,
    ) -> None:
        if not sender_email:
            raise ValueError("Resend sender email is required")
        if not webhook_secret:
            raise ValueError("Resend webhook secret is required")
        self._sender_email = sender_email
        self._sender = sender
        self._webhook_secret = webhook_secret
        self._verifier = verifier

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
            raise IdentityError(
                "auth.provider_unavailable", status=503, recovery="retry_later"
            )
        try:
            result = self._sender(
                {
                    "from": self._sender_email,
                    "to": [normalized_email],
                    "subject": "Tu enlace para ingresar a Umbral",
                    "html": (
                        "<p>Tu enlace para ingresar a Umbral</p>"
                        f'<p><a href="{capture_url}">Ingresá a Umbral</a></p>'
                    ),
                    "text": (
                        "Tu enlace para ingresar a Umbral\n\n"
                        f"Ingresá a Umbral: {capture_url}"
                    ),
                    "tags": [{"name": "attempt_id", "value": str(attempt_id)}],
                },
                {"idempotency_key": idempotency_key},
            )
            return EmailAcceptance("resend", str(result["id"]), now)
        except Exception as exc:
            raise IdentityError(
                "auth.provider_unavailable", status=503, recovery="retry_later"
            ) from exc

    def verify_webhook(
        self,
        *,
        raw_body: bytes,
        headers: Mapping[str, str],
        received_at: datetime,
    ) -> Mapping[str, str] | None:
        if self._verifier is None:
            raise IdentityError(
                "auth.provider_unavailable", status=503, recovery="retry_later"
            )
        try:
            payload = self._verifier(
                {
                    "payload": raw_body.decode("utf-8"),
                    "headers": {
                        "id": headers.get("svix-id", ""),
                        "timestamp": headers.get("svix-timestamp", ""),
                        "signature": headers.get("svix-signature", ""),
                    },
                    "webhook_secret": self._webhook_secret,
                }
            )
            if not isinstance(payload, Mapping):
                raise ValueError("verified webhook payload is not an object")
            verified_payload = cast(Mapping[str, object], payload)
            data = verified_payload.get("data")
            if not isinstance(data, Mapping):
                raise ValueError("verified webhook payload has no data object")
            verified_data = cast(Mapping[str, object], data)
            event_id = verified_payload.get("id")
            event_type = verified_payload.get("type")
            email_id = verified_data.get("email_id")
            if (
                not isinstance(event_id, str)
                or not isinstance(event_type, str)
                or not isinstance(email_id, str)
            ):
                raise ValueError("verified webhook payload is incomplete")
            return {"id": event_id, "type": event_type, "email_id": email_id}
        except (UnicodeDecodeError, TypeError, ValueError, KeyError) as exc:
            raise IdentityError(
                "auth.webhook_invalid", status=401, recovery="none"
            ) from exc

    def health(self) -> str:
        return "ready" if self._sender is not None else "unavailable"
