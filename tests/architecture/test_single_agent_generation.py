"""Single-generation guard: only one executable agent path may exist."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
CONTRACTS = ROOT / "contracts" / "agent"

FORBIDDEN = re.compile(
    r"AgentGraphV\d|build_graph_v\d|build_topology_v\d|conversation\.v\d"
)


def production_python_files() -> list[Path]:
    return [p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts]


def find_source_hits(files: list[Path], pattern: re.Pattern[str]) -> list[str]:
    hits: list[str] = []
    for path in sorted(files):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{lineno}:{line.strip()[:200]}")
    return hits


def contract_paths() -> list[str]:
    if not CONTRACTS.exists():
        return []
    return sorted(
        p.relative_to(ROOT).as_posix()
        for p in CONTRACTS.glob("*.json")
        if p.is_file()
    )


def test_only_one_agent_generation_is_executable() -> None:
    assert find_source_hits(production_python_files(), FORBIDDEN) == []


def test_only_unversioned_agent_contracts_exist() -> None:
    assert contract_paths() == [
        "contracts/agent/interpretation-schema.json",
        "contracts/agent/reply-schema.json",
        "contracts/agent/state-schema.json",
    ]
