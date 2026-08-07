"""Module-level boundary fixtures for the scoring seams.

The Import Linter contracts in ``pyproject.toml`` already enforce the layer
rules; these fixtures pin the scoring-specific seams explicitly so a
regression in ``application/scoring`` is caught by name.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).parents[2] / "src" / "umbral"

_APPLICATION_FORBIDDEN = (
    "umbral.infrastructure",
    "umbral.agent",
    "umbral.api",
    "umbral.workers",
    "fastapi",
    "pydantic",
    "sqlalchemy",
    "alembic",
    "geoalchemy2",
    "httpx",
    "rq",
    "redis",
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


def test_application_scoring_has_no_infrastructure_or_web_dependencies() -> None:
    violations = _collect_violations(
        _SRC / "application" / "scoring", _APPLICATION_FORBIDDEN
    )
    assert violations == []


def test_workers_radar_imports_only_application_boundaries() -> None:
    source = Path(_SRC / "workers" / "radar.py")
    assert source.exists()
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for module in _imported_modules(tree):
        if module.startswith("umbral.infrastructure"):
            raise AssertionError(f"workers/radar.py must not import {module}")
