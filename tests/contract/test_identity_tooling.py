from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_identity_tooling_is_declared_for_local_and_ci_runs() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package = json.loads(
        (ROOT / "apps" / "web" / "package.json").read_text(encoding="utf-8")
    )
    workflow = (ROOT / ".github" / "workflows" / "check.yml").read_text(
        encoding="utf-8"
    )

    assert '"pytest-asyncio' in pyproject
    assert '"identity:' in pyproject
    assert "asyncio_mode = \"auto\"" in pyproject
    assert "test:identity" in package["scripts"]
    assert "test:e2e:identity" in package["scripts"]
    assert "tests/unit/identity" in workflow
    assert "test:identity" in workflow
