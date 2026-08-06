"""Module-level boundary fixtures for the ingestion seams.

The Import Linter contracts in ``pyproject.toml`` already enforce the layer
rules; these fixtures pin the ingestion-specific seams explicitly so a
regression in ``application/ingestion`` or ``infrastructure/sources`` is
caught by name.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).parents[2] / "src" / "umbral"

_INGESTION_FORBIDDEN = (
    "umbral.infrastructure",
    "umbral.agent",
    "umbral.api",
    "umbral.workers",
    "fastapi",
    "pydantic",
    "sqlalchemy",
    "alembic",
    "rq",
    "redis",
    "boto3",
)
_SOURCES_FORBIDDEN = (
    "umbral.agent",
    "umbral.api",
    "umbral.workers",
    "fastapi",
    "sqlalchemy",
    "boto3",
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


def _collect_violations(package: Path, forbidden: tuple[str, ...]) -> list[str]:
    violations: list[str] = []
    for source in sorted(package.glob("*.py")):
        if source.name == "__init__.py":
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for module in _imported_modules(tree):
            if any(
                module == item or module.startswith(f"{item}.") for item in forbidden
            ):
                violations.append(f"{source.name} -> {module}")
    return violations


def test_application_ingestion_has_no_infrastructure_or_web_dependencies() -> None:
    violations = _collect_violations(
        _SRC / "application" / "ingestion", _INGESTION_FORBIDDEN
    )
    assert violations == []


def test_infrastructure_sources_has_no_runtime_surface_dependencies() -> None:
    violations = _collect_violations(
        _SRC / "infrastructure" / "sources", _SOURCES_FORBIDDEN
    )
    assert violations == []
