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


def _imported_modules(tree: ast.Module) -> list[str]:
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
            modules.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def test_preferences_has_no_infrastructure_or_web_dependencies() -> None:
    violations: list[str] = []
    for source in sorted(_SRC.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for module in _imported_modules(tree):
            if any(
                module == item or module.startswith(f"{item}.") for item in _FORBIDDEN
            ):
                violations.append(f"{source.name} -> {module}")
    assert violations == []


def test_boundary_collector_catches_direct_and_from_imports() -> None:
    tree = ast.parse("import sqlalchemy\nfrom umbral.infrastructure import db")

    assert _imported_modules(tree) == [
        "sqlalchemy",
        "umbral.infrastructure",
        "umbral.infrastructure.db",
    ]
