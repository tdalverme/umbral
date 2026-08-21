"""Loads the active import contract v2 from the repository contracts tree."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.application.ingestion.import_contract import ContractSpec, parse_contract

_CONTRACT_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "import"
    / "v2"
    / "import-contract.json"
)


def load_contract_v2(path: Path | None = None) -> ContractSpec:
    source = path or _CONTRACT_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    return parse_contract(data)
