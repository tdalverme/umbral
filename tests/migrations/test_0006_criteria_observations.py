"""Criteria migration contract tests (deterministic, no Docker)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from umbral.infrastructure.db.migrations import expected_schema

CRITERIA_TABLES = {
    "concepts",
    "concept_versions",
    "preference_facts",
    "profile_criteria_compilations",
    "listing_observations",
    "extraction_versions",
    "recomputation_runs",
    "listing_embeddings",
    "urban_signals",
}


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0006_criteria_observations.py")
    spec = importlib.util.spec_from_file_location("criteria_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_criteria_revision_links_to_radar_head() -> None:
    revision = _revision_module()
    assert revision.revision == "0006_criteria_observations"
    assert revision.down_revision == "0005_search_radar"


def test_criteria_tables_are_declared_in_expected_schema() -> None:
    schema = expected_schema()
    assert set(schema.tables).issuperset(CRITERIA_TABLES)


def test_criteria_unique_and_check_constraints_are_declared() -> None:
    schema = expected_schema()
    observations = schema.tables["listing_observations"]
    concepts = schema.tables["concepts"]
    facts = schema.tables["preference_facts"]
    assert any(c.name == "uq_concepts_key" for c in concepts.constraints)
    assert any(c.name == "ck_concepts_key_format" for c in concepts.constraints)
    assert any(c.name == "uq_listing_observations_active" for c in observations.indexes)
    assert any(
        c.name == "ck_listing_observations_score" for c in observations.constraints
    )
    assert any(
        c.name == "ck_listing_observations_state_failure"
        for c in observations.constraints
    )
    assert any(c.name == "uq_preference_facts_active" for c in facts.indexes)
    assert any(c.name == "ck_preference_facts_weight" for c in facts.constraints)


def test_criteria_migration_uses_postgis_and_vector_extensions() -> None:
    source = Path("alembic/versions/0006_criteria_observations.py").read_text(
        encoding="utf-8"
    )
    assert "CREATE EXTENSION IF NOT EXISTS postgis" in source
    assert "CREATE EXTENSION IF NOT EXISTS vector" in source
    assert "DROP TYPE IF EXISTS" in source
