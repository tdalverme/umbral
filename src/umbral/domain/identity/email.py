"""Versioned, conservative email normalization for the closed beta cohort."""
# ruff: noqa: E501

from __future__ import annotations

import re
from dataclasses import dataclass

NORMALIZATION_VERSION = 1
_EMAIL = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


@dataclass(frozen=True, slots=True)
class EmailAddress:
    value: str
    normalization_version: int = NORMALIZATION_VERSION

    def __post_init__(self) -> None:
        if self.normalization_version != NORMALIZATION_VERSION:
            raise ValueError("unsupported email normalization version")
        if not _EMAIL.fullmatch(self.value) or len(self.value) > 320:
            raise ValueError("invalid email address")


def normalize_email(raw: str) -> EmailAddress:
    """Trim ASCII surrounding whitespace and lowercase both address parts."""

    if not isinstance(raw, str):
        raise ValueError("email must be text")
    value = raw.strip(" \t\r\n\f\v").lower()
    if not _EMAIL.fullmatch(value) or ".." in value or value.startswith(".") or value.endswith(".") or len(value) < 3 or len(value) > 320:
        raise ValueError("invalid email address")
    return EmailAddress(value)
