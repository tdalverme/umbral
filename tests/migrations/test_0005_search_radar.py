"""Search radar migration contract tests (deterministic, no Docker)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from umbral.infrastructure.db.migrations import expected_schema

RADAR_TABLES = {
    "search_profiles",
    "search_profile_versions",
    "recommendation_runs",
    "recommendation_items",
    "product_events",
}


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0005_search_radar.py")
    spec = importlib.util.spec_from_file_location("radar_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_radar_revision_links_to_silver_head() -> None:
    revision = _revision_module()
    assert revision.revision == "0005_search_radar"
    assert revision.down_revision == "0004_silver_normalization"


def test_radar_tables_are_declared_in_expected_schema() -> None:
    schema = expected_schema()
    assert set(schema.tables).issuperset(RADAR_TABLES)


def test_radar_unique_and_check_constraints_are_declared() -> None:
    profiles = expected_schema().tables["search_profiles"]
    versions = expected_schema().tables["search_profile_versions"]
    runs = expected_schema().tables["recommendation_runs"]
    items = expected_schema().tables["recommendation_items"]
    assert any(c.name == "uq_search_profiles_owner_name" for c in profiles.constraints)
    assert any(
        c.name == "uq_search_profile_versions_profile_version"
        for c in versions.constraints
    )
    assert any(
        c.name == "uq_recommendation_runs_profile_version" for c in runs.constraints
    )
    assert any(
        c.name == "uq_recommendation_items_run_position" for c in items.constraints
    )
    assert any(c.name == "ck_search_profiles_budget" for c in profiles.constraints)


def test_radar_downgrade_drops_types() -> None:
    revision = _revision_module()
    source = Path("alembic/versions/0005_search_radar.py").read_text(encoding="utf-8")
    assert "search_profile_state" in source
    assert "recommendation_run_state" in source
    assert callable(revision.downgrade)
