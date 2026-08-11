"""Notification email adapters (H5, UM-H5-013).

The recording adapter keeps every message in memory (0 provider, 0 tracking)
for local/E2E; the Resend adapter mirrors the identity pattern through an
injected ``sender`` so the provider client stays behind the port.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from uuid import UUID


class NotificationDeliveryError(Exception):
    """A typed, retryable notification email failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class RecordingNotificationEmailAdapter:
    """Deterministic email adapter for tests and local runs."""

    provider = "recording"

    def __init__(self) -> None:
        self.messages: list[Mapping[str, object]] = []
        self.fail_send = False

    def send_decision_email(
        self,
        *,
        to_email: str,
        subject: str,
        body_html: str,
        decision_id: UUID,
        provider_message_id: str,
        now: datetime,
        correlation_id: UUID | None = None,
    ) -> str:
        if self.fail_send:
            raise NotificationDeliveryError("email.provider_unavailable")
        message_id = f"recording-{provider_message_id}"
        self.messages.append(
            {
                "to": to_email,
                "subject": subject,
                "html": body_html,
                "decision_id": str(decision_id),
                "message_id": message_id,
                "correlation_id": str(correlation_id) if correlation_id else None,
            }
        )
        return message_id


class ResendNotificationEmailAdapter:
    """Resend transactional adapter reusing the shared provider client."""

    provider = "resend"

    def __init__(
        self,
        *,
        sender_email: str,
        sender: Callable[
            [Mapping[str, object], Mapping[str, str]], Mapping[str, object]
        ],
    ) -> None:
        if not sender_email:
            raise ValueError("notification sender email is required")
        if sender is None:
            raise ValueError("notification sender is required")
        self._sender_email = sender_email
        self._sender = sender

    def send_decision_email(
        self,
        *,
        to_email: str,
        subject: str,
        body_html: str,
        decision_id: UUID,
        provider_message_id: str,
        now: datetime,
        correlation_id: UUID | None = None,
    ) -> str:
        try:
            result = self._sender(
                {
                    "from": self._sender_email,
                    "to": [to_email],
                    "subject": subject,
                    "html": body_html,
                    "tags": [
                        {"name": "decision_id", "value": str(decision_id)},
                        *(
                            [
                                {
                                    "name": "correlation_id",
                                    "value": str(correlation_id),
                                }
                            ]
                            if correlation_id is not None
                            else []
                        ),
                    ],
                },
                {"idempotency_key": provider_message_id},
            )
        except Exception as exc:  # noqa: BLE001 - provider failure is typed
            raise NotificationDeliveryError("email.provider_unavailable") from exc
        message_id = result.get("id")
        if not isinstance(message_id, str):
            raise NotificationDeliveryError("email.provider_reply_invalid")
        return message_id
