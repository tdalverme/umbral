"""Migration graph and metadata drift contracts (T037)."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from umbral.infrastructure.db.base import metadata
from umbral.infrastructure.db.migrations import expected_schema


def _script_directory() -> ScriptDirectory:
    config = Config(str(Path("alembic.ini")))
    config.set_main_option("script_location", "alembic")
    return ScriptDirectory.from_config(config)


def test_migration_graph_has_one_linear_head() -> None:
    heads = _script_directory().get_heads()

    assert heads == ["0001_foundation_runtime"]


def test_bootstrap_metadata_matches_declared_schema_without_drift() -> None:
    assert expected_schema() == metadata


def test_downgrade_policy_is_explicitly_empty_only() -> None:
    revision = _script_directory().get_revision("0001_foundation_runtime")

    assert revision is not None
    assert revision.down_revision is None
    assert "empty" in (revision.doc or "").lower()

