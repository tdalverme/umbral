"""Recommendation narrative cache migration contract tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from umbral.infrastructure.db.migrations import expected_schema


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0025_recommendation_narratives.py")
    spec = importlib.util.spec_from_file_location(
        "recommendation_narratives_revision", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recommendation_narratives_revision_follows_current_head() -> None:
    revision = _revision_module()
    assert revision.revision == "0025_recommendation_narratives"
    assert revision.down_revision == "0024_conversation_v5_proposal_total"


def test_recommendation_narratives_is_versioned_by_run_and_generator() -> None:
    narratives = expected_schema().tables["recommendation_narratives"]
    for column in (
        "run_id",
        "listing_id",
        "prompt_version",
        "model_version",
        "schema_version",
        "text",
        "used_criteria",
        "used_evidence_refs",
        "narrative_source",
        "output_model_version",
    ):
        assert column in narratives.c

    constraints = {constraint.name for constraint in narratives.constraints}
    assert "uq_recommendation_narratives_cache_key" in constraints
    assert "ck_recommendation_narratives_text" in constraints
    assert "ck_recommendation_narratives_source" in constraints
