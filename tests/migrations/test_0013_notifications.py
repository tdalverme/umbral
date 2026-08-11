"""Notification migration contract tests (deterministic, no Docker)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from umbral.infrastructure.db.migrations import expected_schema


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0013_notifications.py")
    spec = importlib.util.spec_from_file_location("notifications_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_notifications_revision_links_to_evals_head() -> None:
    revision = _revision_module()
    assert revision.revision == "0013_notifications"
    assert revision.down_revision == "0012_agent_evals"


def test_notification_tables_are_declared() -> None:
    schema = expected_schema()
    assert "notification_preferences" in schema.tables
    assert "notification_decisions" in schema.tables
    assert "notification_inbox_items" in schema.tables


def test_notification_decision_columns_are_declared() -> None:
    schema = expected_schema()
    decisions = schema.tables["notification_decisions"]
    for column in (
        "user_id",
        "search_profile_id",
        "recommendation_item_id",
        "trigger",
        "reason_code",
        "policy_version",
        "decision_state",
    ):
        assert column in decisions.columns, column
