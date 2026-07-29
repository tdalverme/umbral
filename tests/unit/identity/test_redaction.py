from __future__ import annotations

from umbral.infrastructure.observability.filtering import redact_identity_payload


def test_recursive_identity_redaction_removes_bearer_and_pii_fields() -> None:
    payload = {
        "email": "person@example.com",
        "nested": [{"token_hash": "secret", "safe": "eligible"}],
        "url": "https://example.invalid/auth/capture?token=secret",
    }
    assert redact_identity_payload(payload) == {
        "nested": [{"safe": "eligible"}]
    }
