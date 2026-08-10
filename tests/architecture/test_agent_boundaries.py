"""Module-level boundary fixtures for the agent and chat seams (H4.1)."""

from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "umbral"

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
    "langgraph",
    "langchain",
)

_AGENT_FORBIDDEN = (
    "umbral.infrastructure",
    "umbral.api",
    "umbral.workers",
    "fastapi",
    "pydantic",
    "pydantic_settings",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "geoalchemy2",
    "pgvector",
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


def _collect_violations(directory: Path, forbidden: tuple[str, ...]) -> list[str]:
    violations: list[str] = []
    if not directory.exists():
        return violations
    for path in sorted(directory.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for module in _imported_modules(tree):
            for prefix in forbidden:
                if module == prefix or module.startswith(f"{prefix}."):
                    violations.append(f"{path.relative_to(_SRC)} -> {module}")
    return violations


def test_application_chat_has_no_infrastructure_or_web_dependencies() -> None:
    violations = _collect_violations(
        _SRC / "application" / "chat", _APPLICATION_FORBIDDEN
    )
    assert violations == []


def test_application_agent_has_no_infrastructure_or_llm_dependencies() -> None:
    violations = _collect_violations(
        _SRC / "application" / "agent", _APPLICATION_FORBIDDEN
    )
    assert violations == []


def test_agent_layer_never_imports_infrastructure() -> None:
    violations = _collect_violations(_SRC / "agent", _AGENT_FORBIDDEN)
    assert violations == []


def test_agent_tools_layer_consumes_only_application_and_domain_ports() -> None:
    # The explicit tool surface is a permissioned contract layer: it may
    # depend on application services and agent/domain contracts, never on
    # infrastructure, API, workers or transport (Principle III, R-01).
    violations = _collect_violations(_SRC / "agent" / "tools", _AGENT_FORBIDDEN)
    assert violations == []


def test_workers_do_not_import_the_agent_runtime() -> None:
    violations = _collect_violations(_SRC / "workers", ("umbral.agent",))
    assert violations == []
