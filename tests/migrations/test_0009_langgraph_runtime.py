"""Conversational runtime migration contract tests (deterministic, no Docker)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from umbral.infrastructure.db.migrations import expected_schema

AGENT_TABLES = {
    "chat_sessions",
    "chat_messages",
    "agent_graph_runs",
    "agent_node_runs",
    "agent_model_calls",
}
LANGGRAPH_TABLES = {
    "checkpoint_migrations",
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
}


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0009_langgraph_runtime.py")
    spec = importlib.util.spec_from_file_location("agent_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_revision_links_to_feedback_head() -> None:
    revision = _revision_module()
    assert revision.revision == "0009_langgraph_runtime"
    assert revision.down_revision == "0008_feedback_learning"


def test_agent_tables_are_declared_in_expected_schema() -> None:
    schema = expected_schema()
    assert set(schema.tables).issuperset(AGENT_TABLES)
    # LangGraph-managed tables are never part of our metadata (R-03).
    assert not (set(schema.tables) & LANGGRAPH_TABLES)


def test_agent_active_run_index_is_declared() -> None:
    schema = expected_schema()
    runs = schema.tables["agent_graph_runs"]
    assert any(
        index.name == "uq_agent_graph_runs_session_active" for index in runs.indexes
    )


def test_agent_migration_declares_the_enum_types() -> None:
    source = Path("alembic/versions/0009_langgraph_runtime.py").read_text(
        encoding="utf-8"
    )
    for enum_name in (
        "chat_session_state",
        "chat_message_role",
        "chat_message_state",
        "agent_run_state",
        "agent_node_kind",
        "agent_call_state",
    ):
        assert enum_name in source
        assert f"DROP TYPE IF EXISTS {enum_name}" in source


def test_agent_migration_has_downgrade_for_all_tables() -> None:
    source = Path("alembic/versions/0009_langgraph_runtime.py").read_text(
        encoding="utf-8"
    )
    for table in ("chat_sessions", "agent_graph_runs", "chat_messages"):
        assert f'"{table}"' in source
