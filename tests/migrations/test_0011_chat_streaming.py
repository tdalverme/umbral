"""Chat streaming migration contract tests (deterministic, no Docker)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from umbral.infrastructure.db.migrations import expected_schema


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0011_chat_streaming.py")
    spec = importlib.util.spec_from_file_location("chat_streaming_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chat_streaming_revision_links_to_agent_tools_head() -> None:
    revision = _revision_module()
    assert revision.revision == "0011_chat_streaming"
    assert revision.down_revision == "0010_agent_tools"


def test_chat_messages_client_message_id_is_declared() -> None:
    schema = expected_schema()
    messages = schema.tables["chat_messages"]
    assert "client_message_id" in messages.columns


def test_chat_messages_idempotency_index_is_declared() -> None:
    schema = expected_schema()
    messages = schema.tables["chat_messages"]
    assert any(
        index.name == "uq_chat_messages_session_client" for index in messages.indexes
    )


def test_proposals_interactive_columns_are_declared() -> None:
    schema = expected_schema()
    proposals = schema.tables["search_profile_update_proposals"]
    assert "rejection_note" in proposals.columns
    assert "superseded_by_proposal_id" in proposals.columns
    assert any(
        index.name == "ix_proposals_superseded_by" for index in proposals.indexes
    )


def test_chat_streaming_migration_has_downgrade() -> None:
    source = Path("alembic/versions/0011_chat_streaming.py").read_text(
        encoding="utf-8"
    )
    assert '"chat_messages"' in source
    assert '"search_profile_update_proposals"' in source
    assert "def downgrade" in source
