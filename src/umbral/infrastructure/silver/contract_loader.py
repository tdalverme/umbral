"""Loads the published Silver contracts from the repository contracts tree."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.application.silver.dedupe_policy import (
    DedupePolicySpec,
    parse_dedupe_policy,
)
from umbral.application.silver.silver_schema import (
    SilverSchemaSpec,
    parse_silver_schema,
)

_SILVER_SCHEMA_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "silver"
    / "v1"
    / "silver-schema.json"
)
_DEDUPE_POLICY_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "dedupe"
    / "v1"
    / "dedupe-policy.json"
)


def load_silver_schema(path: Path | None = None) -> SilverSchemaSpec:
    source = path or _SILVER_SCHEMA_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    return parse_silver_schema(data)


def load_dedupe_policy(path: Path | None = None) -> DedupePolicySpec:
    source = path or _DEDUPE_POLICY_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    return parse_dedupe_policy(data)
