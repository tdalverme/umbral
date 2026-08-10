"""Agent eval migration contract tests (deterministic, no Docker)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from umbral.infrastructure.db.migrations import expected_schema


def _revision_module() -> ModuleType:
    path = Path("alembic/versions/0012_agent_evals.py")
    spec = importlib.util.spec_from_file_location("agent_evals_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_evals_revision_links_to_chat_streaming_head() -> None:
    revision = _revision_module()
    assert revision.revision == "0012_agent_evals"
    assert revision.down_revision == "0011_chat_streaming"


def test_eval_tables_are_declared() -> None:
    schema = expected_schema()
    assert "agent_eval_suites" in schema.tables
    assert "agent_eval_case_results" in schema.tables


def test_eval_suite_columns_are_declared() -> None:
    schema = expected_schema()
    suites = schema.tables["agent_eval_suites"]
    for column in (
        "dataset_version",
        "baseline_release_id",
        "candidate_release_id",
        "gateway_fidelity",
        "status",
        "blocked_reasons",
        "metrics",
        "started_at",
        "finished_at",
    ):
        assert column in suites.columns


def test_eval_case_result_columns_are_declared() -> None:
    schema = expected_schema()
    results = schema.tables["agent_eval_case_results"]
    for column in (
        "eval_suite_id",
        "case_id",
        "tool_selection_ok",
        "args_valid",
        "grounding_ok",
        "confirmation_ok",
        "outcome_ok",
        "cost_usd",
        "latency_ms",
        "verdict",
    ):
        assert column in results.columns


def test_graph_runs_release_id_is_declared() -> None:
    schema = expected_schema()
    runs = schema.tables["agent_graph_runs"]
    assert "release_id" in runs.columns


def test_agent_evals_migration_has_downgrade() -> None:
    source = Path("alembic/versions/0012_agent_evals.py").read_text(encoding="utf-8")
    assert '"agent_eval_suites"' in source
    assert '"agent_eval_case_results"' in source
    assert '"agent_graph_runs"' in source
    assert "def downgrade" in source
