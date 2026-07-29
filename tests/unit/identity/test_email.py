from __future__ import annotations

import pytest

from umbral.domain.identity.email import normalize_email


def test_normalization_is_conservative_and_versioned() -> None:
    assert normalize_email("  PERSON@Example.COM\n").value == "person@example.com"
    assert normalize_email("A+B@example.com").value == "a+b@example.com"


@pytest.mark.parametrize("value", ["", "invalid", "a@", "a@example", "x@y..z"])
def test_invalid_email_is_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_email(value)
