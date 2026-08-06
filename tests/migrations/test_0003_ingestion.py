"""Bronze ingestion migration contract tests (deterministic, no Docker)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from umbral.infrastructure.db.migrations import expected_schema

INGESTION_TABLES = {"import_runs", "raw_listing_snapshots", "quarantine_records"}


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0003_bronze_ingestion.py")
    spec = importlib.util.spec_from_file_location("ingestion_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ingestion_revision_links_to_identity_head() -> None:
    revision = _revision_module()
    assert revision.revision == "0003_bronze_ingestion"
    assert revision.down_revision == "0002_private_beta_identity"


def test_ingestion_tables_are_declared_in_expected_schema() -> None:
    schema = expected_schema()
    assert set(schema.tables).issuperset(INGESTION_TABLES)


def test_ingestion_unique_and_check_constraints_are_declared() -> None:
    import_runs = expected_schema().tables["import_runs"]
    snapshots = expected_schema().tables["raw_listing_snapshots"]
    assert any(c.name == "uq_import_runs_source_batch" for c in import_runs.constraints)
    assert any(
        c.name == "uq_raw_listing_snapshots_content" for c in snapshots.constraints
    )


def test_ingestion_downgrade_drops_types() -> None:
    revision = _revision_module()
    source = Path("alembic/versions/0003_bronze_ingestion.py").read_text(
        encoding="utf-8"
    )
    assert "import_run_state" in source
    assert "import_format" in source
    assert callable(revision.downgrade)
