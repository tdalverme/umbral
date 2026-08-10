"""Reply schema v2 conformance (FR-011, T015)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPLY_CONTRACT = json.loads(
    (ROOT / "contracts" / "agent" / "v2" / "reply-schema-v2.json").read_text(
        encoding="utf-8"
    )
)


def test_reply_v2_contract_declares_tool_calls_bounded() -> None:
    assert REPLY_CONTRACT["contract_version"] == "2"
    assert REPLY_CONTRACT["registry_version"] == "agent-reply-schema-v2"
    assert REPLY_CONTRACT["schema_version"] == "reply-v2"
    fields = REPLY_CONTRACT["fields"]
    assert "reply_text" in fields
    assert "refs" in fields
    tool_calls = fields["tool_calls"]
    assert tool_calls["kind"] == "list"
    assert tool_calls["max_items"] == 5
    item = tool_calls["item"]
    assert set(item) == {"tool", "args"}
