"""Agent tools migration contract tests (deterministic, no Docker)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from umbral.infrastructure.db.migrations import expected_schema

PROPOSAL_TABLES = {"search_profile_update_proposals"}


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0010_agent_tools.py")
    spec = importlib.util.spec_from_file_location("agent_tools_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_tools_revision_links_to_langgraph_head() -> None:
    revision = _revision_module()
    assert revision.revision == "0010_agent_tools"
    assert revision.down_revision == "0009_langgraph_runtime"


def test_proposal_table_is_declared_in_expected_schema() -> None:
    schema = expected_schema()
    assert set(schema.tables).issuperset(PROPOSAL_TABLES)


def test_proposal_idempotency_index_is_declared() -> None:
    schema = expected_schema()
    proposals = schema.tables["search_profile_update_proposals"]
    assert any(
        index.name == "uq_proposals_profile_idempotency"
        for index in proposals.indexes
    )


def test_agent_tools_migration_declares_the_enum_type() -> None:
    source = Path("alembic/versions/0010_agent_tools.py").read_text(
        encoding="utf-8"
    )
    assert "proposal_state" in source
    assert "DROP TYPE IF EXISTS proposal_state" in source


def test_agent_tools_migration_has_downgrade_for_the_table() -> None:
    source = Path("alembic/versions/0010_agent_tools.py").read_text(
        encoding="utf-8"
    )
    assert '"search_profile_update_proposals"' in source
