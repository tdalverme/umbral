"""Architecture boundaries: notifications application layer stays pure (H5)."""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

APPLICATION_ROOT = Path("src/umbral/application/notifications")
FORBIDDEN = {
    "fastapi",
    "sqlalchemy",
    "redis",
    "alembic",
    "rq",
    "uvicorn",
    "httpx",
}


def _modules() -> list[Path]:
    return sorted(APPLICATION_ROOT.rglob("*.py"))


def test_notifications_application_imports_no_infrastructure() -> None:
    forbidden_hits: list[str] = []
    for module in _modules():
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in FORBIDDEN or root in {"infrastructure", "workers"}:
                        forbidden_hits.append(f"{module.name}: {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root in FORBIDDEN or root in {"infrastructure", "workers"}:
                    forbidden_hits.append(f"{module.name}: {node.module}")
    assert not forbidden_hits, forbidden_hits


def test_notifications_application_modules_import() -> None:
    for module in _modules():
        spec = importlib.util.spec_from_file_location(
            "notifications_test", module
        )
        assert spec is not None, module.name
        assert spec.loader is not None, module.name
        loaded = importlib.util.module_from_spec(spec)
        sys.modules["notifications_test"] = loaded
        try:
            spec.loader.exec_module(loaded)
        except Exception as exc:  # noqa: BLE001 - report which module fails
            raise AssertionError(f"{module.name}: {exc}") from exc
