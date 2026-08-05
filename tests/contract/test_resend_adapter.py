from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import uuid4

from umbral.infrastructure.email.resend import ResendEmailAdapter


def test_resend_adapter_sends_a_non_tracking_magic_link_with_idempotency() -> None:
    calls: list[tuple[Mapping[str, object], Mapping[str, str] | None]] = []

    def sender(
        params: Mapping[str, object], options: Mapping[str, str] | None
    ) -> dict[str, object]:
        calls.append((params, options))
        return {"id": "msg-1"}

    attempt_id = uuid4()
    capture_url = (
        "https://preview.umbral.invalid/auth/capture?attempt_id=123&token_hash=opaque"
    )
    adapter = ResendEmailAdapter(
        sender_email="Umbral <onboarding@resend.dev>",
        webhook_secret="whsec_dGVzdC13ZWJob29rLXNlY3JldA==",
        sender=sender,
    )

    adapter.send_magic_link(
        attempt_id=attempt_id,
        normalized_email="owner@example.com",
        capture_url=capture_url,
        expires_at=datetime.now(timezone.utc),
        idempotency_key="identity.magic-link/1",
        now=datetime.now(timezone.utc),
    )

    assert calls == [
        (
            {
                "from": "Umbral <onboarding@resend.dev>",
                "to": ["owner@example.com"],
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
            {"idempotency_key": "identity.magic-link/1"},
        )
    ]
