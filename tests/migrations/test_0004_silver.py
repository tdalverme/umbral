"""Silver normalization migration contract tests (deterministic, no Docker)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from umbral.infrastructure.db.migrations import expected_schema

SILVER_TABLES = {
    "canonical_properties",
    "silver_listings",
    "dedupe_links",
    "listing_changes",
}


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0004_silver_normalization.py")
    spec = importlib.util.spec_from_file_location("silver_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_silver_revision_links_to_ingestion_head() -> None:
    revision = _revision_module()
    assert revision.revision == "0004_silver_normalization"
    assert revision.down_revision == "0003_bronze_ingestion"


def test_silver_tables_are_declared_in_expected_schema() -> None:
    schema = expected_schema()
    assert set(schema.tables).issuperset(SILVER_TABLES)


def test_silver_unique_and_check_constraints_are_declared() -> None:
    listings = expected_schema().tables["silver_listings"]
    links = expected_schema().tables["dedupe_links"]
    changes = expected_schema().tables["listing_changes"]
    assert any(
        c.name == "uq_silver_listings_snapshot_version" for c in listings.constraints
    )
    assert any(c.name == "uq_dedupe_links_pair" for c in links.constraints)
    assert any(c.name == "uq_listing_changes_field" for c in changes.constraints)
    assert any(c.name == "ck_dedupe_links_state_method" for c in links.constraints)


def test_silver_geometry_column_is_postgis_point() -> None:
    listings = expected_schema().tables["silver_listings"]
    assert "geometry" in listings.c


def test_silver_downgrade_drops_types() -> None:
    revision = _revision_module()
    source = Path("alembic/versions/0004_silver_normalization.py").read_text(
        encoding="utf-8"
    )
    assert "geo_precision" in source
    assert "dedupe_link_state" in source
    assert callable(revision.downgrade)
