"""Boundary checks for the preference expression application seam."""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).parents[2] / "src" / "umbral" / "application" / "preferences"
_FORBIDDEN = (
    "umbral.infrastructure",
    "umbral.agent",
    "umbral.api",
    "umbral.workers",
    "fastapi",
    "pydantic",
    "sqlalchemy",
    "alembic",
    "pgvector",
)


def test_preferences_has_no_infrastructure_or_web_dependencies() -> None:
    violations: list[str] = []
    for source in sorted(_SRC.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            module = node.module if isinstance(node, ast.ImportFrom) else None
            if module and any(
                module == item or module.startswith(f"{item}.") for item in _FORBIDDEN
            ):
                violations.append(f"{source.name} -> {module}")
    assert violations == []
