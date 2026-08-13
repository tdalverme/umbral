"""Reply schema v1 conformance (FR-010..FR-012)."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.infrastructure.agent.model_gateway.managed import _validated_content

ROOT = Path(__file__).resolve().parents[2]
REPLY_CONTRACT = json.loads(
    (ROOT / "contracts" / "agent" / "v1" / "reply-schema-v1.json").read_text(
        encoding="utf-8"
    )
)


def test_reply_contract_declares_fields_and_versions() -> None:
    assert REPLY_CONTRACT["contract_version"] == "1"
    assert REPLY_CONTRACT["registry_version"] == "agent-reply-schema-v1"
    assert REPLY_CONTRACT["schema_version"] == "reply-v1"
    fields = REPLY_CONTRACT["fields"]
    assert fields["reply_text"]["kind"] == "string"
    assert fields["reply_text"]["max_length"] == 2000
    assert fields["reply_text"]["required"] is True
    assert fields["refs"]["kind"] == "list"


def test_valid_reply_content_is_accepted() -> None:
    body = {"content": {"reply_text": "ok", "refs": [{"entity": "listing", "id": "x"}]}}
    content = _validated_content(body, {"reply_text": {}, "refs": {}})
    assert content is not None
    assert content["reply_text"] == "ok"


def test_invalid_reply_content_is_rejected() -> None:
    reply_schema: dict[str, object] = {"reply_text": {}, "refs": {}}
    assert _validated_content({"content": {}}, reply_schema) is None
    assert (
        _validated_content({"content": {"reply_text": "", "refs": []}}, reply_schema)
        is None
    )
    assert (
        _validated_content(
            {"content": {"reply_text": "x", "refs": "nope"}}, reply_schema
        )
        is None
    )
    assert (
        _validated_content(
            {"content": {"reply_text": "x", "refs": [{"entity": 1, "id": "a"}]}},
            reply_schema,
        )
        is None
    )
    assert _validated_content({}, reply_schema) is None
