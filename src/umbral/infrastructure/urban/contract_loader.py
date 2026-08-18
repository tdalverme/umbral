"""Loads the published urban contract from the repository contracts tree."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.application.urban.contract import (
    UrbanContract,
    parse_urban_contract,
)

_URBAN_CONTRACT_PATH = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "urban"
    / "v1"
    / "urban-contract-v1.json"
)


def load_urban_contract_published(path: Path | None = None) -> UrbanContract:
    source = path or _URBAN_CONTRACT_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        from umbral.application.urban.contract import UrbanContractInvalid

        raise UrbanContractInvalid("published contract must be an object")
    return parse_urban_contract(data)