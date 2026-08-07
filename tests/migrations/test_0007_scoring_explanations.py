"""Scoring migration contract tests (deterministic, no Docker)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from umbral.infrastructure.db.migrations import expected_schema

SCORING_TABLES = {
    "scoring_policies",
    "scoring_policy_versions",
    "criterion_evaluations",
    "comparison_shortlists",
}


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0007_scoring_explanations.py")
    spec = importlib.util.spec_from_file_location("scoring_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scoring_revision_links_to_criteria_head() -> None:
    revision = _revision_module()
    assert revision.revision == "0007_scoring_explanations"
    assert revision.down_revision == "0006_criteria_observations"


def test_scoring_tables_are_declared_in_expected_schema() -> None:
    schema = expected_schema()
    assert set(schema.tables).issuperset(SCORING_TABLES)


def test_scoring_unique_and_check_constraints_are_declared() -> None:
    schema = expected_schema()
    evaluations = schema.tables["criterion_evaluations"]
    policies = schema.tables["scoring_policies"]
    versions = schema.tables["scoring_policy_versions"]
    shortlists = schema.tables["comparison_shortlists"]
    assert any(
        c.name == "uq_criterion_evaluations_run_listing_criterion"
        for c in evaluations.constraints
    )
    assert any(
        c.name == "ck_criterion_evaluations_score" for c in evaluations.constraints
    )
    assert any(c.name == "uq_scoring_policies_key" for c in policies.constraints)
    assert any(
        c.name == "uq_scoring_policy_versions_policy_version"
        for c in versions.constraints
    )
    assert any(
        c.name == "uq_comparison_shortlists_profile_listing"
        for c in shortlists.constraints
    )


def test_scoring_migration_declares_the_evaluation_state_type() -> None:
    source = Path("alembic/versions/0007_scoring_explanations.py").read_text(
        encoding="utf-8"
    )
    assert "evaluation_state" in source
    assert "DROP TYPE IF EXISTS evaluation_state" in source
