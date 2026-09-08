"""Contract checks for the closed explanation-narrative model output."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema  # type: ignore[import-untyped]
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (
        ROOT / "contracts" / "scoring" / "v1" / "explanation-narrative-schema.json"
    ).read_text(encoding="utf-8")
)


def test_narrative_schema_is_closed_and_bounded() -> None:
    """Unbounded structured output could introduce unreviewed claims."""
    assert SCHEMA["type"] == "object"
    assert SCHEMA["additionalProperties"] is False
    assert SCHEMA["required"] == ["text", "used_criteria", "used_evidence_refs"]
    assert SCHEMA["properties"]["text"] == {
        "type": "string",
        "minLength": 1,
        "maxLength": 900,
    }
    assert SCHEMA["properties"]["used_criteria"]["maxItems"] == 6
    assert SCHEMA["properties"]["used_evidence_refs"]["maxItems"] == 12


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "Encaja.", "used_criteria": [], "used_evidence_refs": [], "score": 1},
        {"text": "", "used_criteria": [], "used_evidence_refs": []},
        {"text": "Encaja.", "used_criteria": [], "used_evidence_refs": [1]},
    ],
)
def test_narrative_schema_rejects_unbounded_or_malformed_output(
    payload: dict[str, object],
) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, SCHEMA)
