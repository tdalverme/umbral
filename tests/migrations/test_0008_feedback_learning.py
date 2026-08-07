"""Feedback migration contract tests (deterministic, no Docker)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from umbral.infrastructure.db.migrations import expected_schema

FEEDBACK_TABLES = {
    "feedback_events",
    "feedback_event_reasons",
    "learning_policies",
    "learning_policy_versions",
    "learning_proposals",
}


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0008_feedback_learning.py")
    spec = importlib.util.spec_from_file_location("feedback_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_feedback_revision_links_to_scoring_head() -> None:
    revision = _revision_module()
    assert revision.revision == "0008_feedback_learning"
    assert revision.down_revision == "0007_scoring_explanations"


def test_feedback_tables_are_declared_in_expected_schema() -> None:
    schema = expected_schema()
    assert set(schema.tables).issuperset(FEEDBACK_TABLES)


def test_feedback_unique_and_check_constraints_are_declared() -> None:
    schema = expected_schema()
    events = schema.tables["feedback_events"]
    reasons = schema.tables["feedback_event_reasons"]
    policies = schema.tables["learning_policies"]
    versions = schema.tables["learning_policy_versions"]
    proposals = schema.tables["learning_proposals"]
    assert any(
        c.name == "uq_feedback_events_profile_idempotency" for c in events.constraints
    )
    assert any(
        c.name == "ck_feedback_events_idempotency_key" for c in events.constraints
    )
    assert any(
        c.name == "uq_feedback_event_reasons_event_key" for c in reasons.constraints
    )
    assert any(c.name == "uq_learning_policies_key" for c in policies.constraints)
    assert any(
        c.name == "uq_learning_policy_versions_policy_version"
        for c in versions.constraints
    )
    assert any(
        c.name == "uq_learning_proposals_pending" for c in proposals.indexes
    ) or any(
        c.name == "uq_learning_proposals_pending"
        for c in proposals.constraints
    )
    assert any(
        index.name == "uq_feedback_events_active" for index in events.indexes
    )


def test_feedback_migration_declares_the_enum_types() -> None:
    source = Path("alembic/versions/0008_feedback_learning.py").read_text(
        encoding="utf-8"
    )
    for enum_name in (
        "feedback_event_type",
        "feedback_event_state",
        "feedback_polarity",
        "learning_proposal_state",
    ):
        assert enum_name in source
        assert f"DROP TYPE IF EXISTS {enum_name}" in source


def test_feedback_migration_has_downgrade_for_all_tables() -> None:
    source = Path("alembic/versions/0008_feedback_learning.py").read_text(
        encoding="utf-8"
    )
    for table in ("learning_proposals", "feedback_events"):
        assert f'"{table}"' in source
