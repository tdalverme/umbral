"""Loads the published agent tool contract from the repository contracts tree."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.agent.tools.contracts import ToolSpec, parse_tool_contract

_TOOL_CONTRACT_PATH = (
    Path(__file__).resolve().parents[5]
    / "contracts"
    / "agent"
    / "tools"
    / "tool-contract-v2.json"
)


def load_tool_contract(path: Path | None = None) -> list[ToolSpec]:
    source = path or _TOOL_CONTRACT_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    return parse_tool_contract(data)
