from __future__ import annotations

from pathlib import Path


def test_provider_decision_record_covers_required_operational_criteria() -> None:
    document = Path(
        "docs/architecture/decisions/0003-identity-and-email-providers.md"
    ).read_text(encoding="utf-8").lower()
    for criterion in (
        "magic link",
        "idempotencia",
        "local/test",
        "postgresql",
        "salida",
        "preview",
        "credenciales",
        "issuer",
    ):
        assert criterion in document
