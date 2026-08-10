"""Loads the published intent contract from the repository contracts tree."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.agent.intent.contracts import IntentContract, parse_intent_contract

_INTENT_CONTRACT_PATH = (
    Path(__file__).resolve().parents[5]
    / "contracts"
    / "agent"
    / "v3"
    / "intent-schema-v3.json"
)


def load_intent_contract(path: Path | None = None) -> IntentContract:
    source = path or _INTENT_CONTRACT_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    return parse_intent_contract(data)
