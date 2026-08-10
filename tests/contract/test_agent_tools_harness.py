"""Agent tools harness conformance (T044, FR-024)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = REPO_ROOT / "scripts" / "check-agent-tools.ps1"

REQUIRED_TEST_PATHS = (
    "tests\\unit\\agent\\tools",
    "tests\\unit\\application\\agent\\tools",
    "tests\\unit\\infrastructure\\agent\\tools",
    "tests\\unit\\config\\test_agent_settings.py",
    "tests\\contract\\test_agent_tools_contract.py",
    "tests\\contract\\test_agent_state_schema_v2.py",
    "tests\\contract\\test_agent_graph_topology_v2.py",
    "tests\\contract\\test_agent_reply_schema_v2.py",
    "tests\\contract\\test_agent_tool_events.py",
    "tests\\contract\\test_agent_tools_harness.py",
    "tests\\architecture\\test_agent_boundaries.py",
    "tests\\integration\\agent\\tools",
    "tests\\migrations\\test_0010_agent_tools.py",
)


def test_harness_script_exists_and_lists_required_paths() -> None:
    assert HARNESS.exists()
    source = HARNESS.read_text(encoding="utf-8")
    for path in REQUIRED_TEST_PATHS:
        assert path in source, f"harness missing required test path: {path}"
