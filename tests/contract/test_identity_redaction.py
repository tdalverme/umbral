from __future__ import annotations

from umbral.infrastructure.observability.filtering import redact_identity_payload


def test_identity_redaction_is_recursive() -> None:
    payload = {
        "event": {
            "email": "person@example.com",
            "nested": [{"token_hash": "abc", "reason": "eligible"}],
        }
    }
    redacted = redact_identity_payload(payload)
    assert redacted == {"event": {"nested": [{"reason": "eligible"}]}}
