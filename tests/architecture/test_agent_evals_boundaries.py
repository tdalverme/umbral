"""Module-level boundary fixtures for the agent evals and ops seams (T048).

The Import Linter contracts in ``pyproject.toml`` already enforce the layer
rules; these fixtures pin the H4.4 seams explicitly: ``application/agent_evals``
and ``application/agent_ops`` stay pure (0 infrastructure/agent/api/workers),
and the eval runner consumes the graph only through the injected ``CaseExecutor``
port (R-03).
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
    "httpx",
    "rq",
    "redis",
    "langgraph",
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


def test_application_agent_evals_has_no_infrastructure_or_web_dependencies() -> None:
    violations = _collect_violations(
        _SRC / "application" / "agent_evals", _APPLICATION_FORBIDDEN
    )
    assert violations == []


def test_application_agent_ops_has_no_infrastructure_or_web_dependencies() -> None:
    violations = _collect_violations(
        _SRC / "application" / "agent_ops", _APPLICATION_FORBIDDEN
    )
    assert violations == []


def test_application_agent_evals_runner_uses_only_the_executor_port() -> None:
    source = _SRC / "application" / "agent_evals" / "runner.py"
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    modules = _imported_modules(tree)
    assert not any(
        module == "umbral.agent" or module.startswith("umbral.agent.")
        for module in modules
    )


def test_agent_evals_regression_is_pure() -> None:
    source = _SRC / "application" / "agent_evals" / "regression.py"
    assert source.exists()
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    for module in _imported_modules(tree):
        if any(
            module == item or module.startswith(f"{item}.")
            for item in ("umbral.infrastructure", "httpx", "requests", "sqlalchemy")
        ):
            raise AssertionError(f"regression.py must not import {module}")
