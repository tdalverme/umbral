"""Conformance tests for the published V5 conversation schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import jsonschema  # type: ignore[import-untyped]
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_NAMES = (
    "context-schema-v5.json",
    "interpretation-schema-v5.json",
    "state-schema-v5.json",
    "reply-schema-v5.json",
    "graph-topology-v5.json",
)


def _schema(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((ROOT / "contracts" / "agent" / "v5" / name).read_text()),
    )


def _interpretation(act: dict[str, object]) -> dict[str, object]:
    return {
        "contract_version": "5",
        "interpretation_version": "conversation-interpretation-v5",
        "model_version": "gpt-4.1-mini",
        "prompt_version": "interpretation-v5",
        "acts": [act],
    }


def _act(kind: str, **fields: object) -> dict[str, object]:
    return {
        "act_id": "act-1",
        "kind": kind,
        "confidence": 0.9,
        "evidence_spans": [{"start": 0, "end": 3, "text": "foo"}],
        **fields,
    }


def test_v5_schemas_are_closed_and_versioned() -> None:
    """An unversioned or open top-level schema would widen the public seam."""
    for name in SCHEMA_NAMES:
        schema = _schema(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["properties"]["contract_version"] == {"const": "5"}
        assert schema["additionalProperties"] is False


def test_interpretation_uses_exactly_ten_closed_discriminated_act_branches() -> None:
    """Changing the model action vocabulary requires a deliberate schema revision."""
    schema = _schema("interpretation-schema-v5.json")
    branches = schema["$defs"]["act"]["oneOf"]

    assert [branch["properties"]["kind"]["const"] for branch in branches] == [
        "create_radar",
        "set_filter",
        "clear_filter",
        "express_desire",
        "revise_desire",
        "withdraw_desire",
        "record_feedback",
        "resolve_pending",
        "query",
        "unsupported_request",
    ]
    assert all(branch["additionalProperties"] is False for branch in branches)


def test_express_desire_without_raw_text_is_invalid() -> None:
    """A durable desire must retain the user's expressed wording."""
    schema = _schema("interpretation-schema-v5.json")
    payload = _interpretation(_act("express_desire", subject_ref="subject:balcony"))

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


@pytest.mark.parametrize(
    "act",
    [
        _act("record_feedback", feedback_type="like"),
        _act("record_feedback", listing_ref="listing:13"),
    ],
)
def test_record_feedback_requires_listing_ref_and_feedback_type(
    act: dict[str, object],
) -> None:
    """Feedback cannot target an unmentioned listing or omit its published type."""
    schema = _schema("interpretation-schema-v5.json")

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_interpretation(act), schema)


@pytest.mark.parametrize(
    "act",
    [
        _act("query", query_text="mostrar resultados", target={}),
        _act("set_filter", filter_key="budget_max", value=1000, payload={}),
    ],
)
def test_act_branches_reject_unrelated_fields(act: dict[str, object]) -> None:
    """Generic target/payload fields would let model output bypass typed acts."""
    schema = _schema("interpretation-schema-v5.json")

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_interpretation(act), schema)
