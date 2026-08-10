"""Agent harness surface contract (FR-019/FR-020, SC-007)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_AGENT_SURFACES = (
    "src/umbral/agent",
    "src/umbral/application/chat",
    "src/umbral/application/agent",
    "src/umbral/infrastructure/agent",
    "contracts/agent/v1/state-schema-v1.json",
    "contracts/agent/v1/graph-topology-v1.json",
    "contracts/agent/v1/reply-schema-v1.json",
    "scripts/check-agent.ps1",
    "alembic/versions/0009_langgraph_runtime.py",
)


def test_agent_surfaces_exist() -> None:
    for surface in _AGENT_SURFACES:
        assert (ROOT / surface).exists(), f"missing agent surface: {surface}"


def test_harness_script_declares_the_expected_test_paths() -> None:
    script = (ROOT / "scripts" / "check-agent.ps1").read_text(encoding="utf-8")
    for path in (
        "tests\\unit\\agent",
        "tests\\unit\\application\\chat",
        "tests\\unit\\application\\agent",
        "tests\\unit\\infrastructure\\agent",
        "tests\\contract\\test_agent_state_schema.py",
        "tests\\contract\\test_agent_graph_topology.py",
        "tests\\contract\\test_agent_reply_schema.py",
        "tests\\contract\\test_agent_chat_events.py",
        "tests\\contract\\test_agent_harness.py",
        "tests\\architecture\\test_agent_boundaries.py",
        "tests\\integration\\agent",
        "tests\\integration\\chat",
        "tests\\migrations\\test_0009_langgraph_runtime.py",
    ):
        assert path in script, f"harness missing test path: {path}"


def test_no_http_chat_contracts_or_tools_are_added() -> None:
    # FR-020: 0 HTTP chat contracts, 0 tools, 0 web chat surfaces.
    assert not (ROOT / "src" / "umbral" / "api" / "routers" / "chat.py").exists()
    assert not list((ROOT / "src" / "umbral" / "api" / "routers").glob("chat*.py"))
    web_chat = ROOT / "apps" / "web" / "src" / "app" / "(protected)" / "chat"
    assert not web_chat.exists()

    topology = json.loads(
        (ROOT / "contracts" / "agent" / "v1" / "graph-topology-v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert topology["tools"] == []
    assert topology["interrupts"] == []
