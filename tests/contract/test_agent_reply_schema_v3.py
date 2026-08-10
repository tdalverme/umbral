"""Reply schema v3 conformance: grounded refs with cap (T017)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPLY_CONTRACT = json.loads(
    (ROOT / "contracts" / "agent" / "v3" / "reply-schema-v3.json").read_text(
        encoding="utf-8"
    )
)


def test_reply_v3_declares_grounded_refs_with_cap() -> None:
    assert REPLY_CONTRACT["contract_version"] == "3"
    assert REPLY_CONTRACT["registry_version"] == "agent-reply-schema-v3"
    assert REPLY_CONTRACT["schema_version"] == "reply-v3"
    fields = REPLY_CONTRACT["fields"]
    assert fields["reply_text"]["min_length"] == 1
    assert fields["reply_text"]["max_length"] == 2000
    assert fields["refs"]["max_items"] == 10
    assert fields["tool_calls"]["max_items"] == 5
