"""Release manifest database revision stays in sync with the migration head.

The release workflow pins `DatabaseRevision` in `.github/workflows/release.yml`;
this contract test fails in CI when the pin goes stale after a new Alembic
migration, forcing the bump before the next release tag.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def _alembic_heads() -> str:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    line = result.stdout.strip().splitlines()[-1]
    return line.split()[0]


def _pinned_revision() -> str:
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"-DatabaseRevision\s+\"([^\"]+)\"", text)
    assert match is not None, "DatabaseRevision not found in release.yml"
    return match.group(1)


def test_release_revision_matches_the_migration_head() -> None:
    assert _pinned_revision() == _alembic_heads(), (
        "release.yml DatabaseRevision is stale: bump it to "
        f"{_alembic_heads()} after the new migration"
    )
