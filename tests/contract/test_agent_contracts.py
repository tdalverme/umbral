"""Conformance tests for the single published conversation schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import jsonschema  # type: ignore[import-untyped]
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_NAMES = (
    "interpretation-schema.json",
    "state-schema.json",
    "reply-schema.json",
)


def _schema(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((ROOT / "contracts" / "agent" / name).read_text()),
    )


def _interpretation(act: dict[str, object]) -> dict[str, object]:
    return {
        "contract_version": "5",
        "interpretation_version": "conversation-interpretation",
        "acts": [act],
    }


def _act(kind: str, **fields: object) -> dict[str, object]:
    return {
        "act_id": "act-1",
        "kind": kind,
        "confidence": 0.9,
        "evidence_text": "foo",
        **fields,
    }


def test_schemas_are_closed_and_versioned() -> None:
    """An unversioned or open top-level schema would widen the public seam."""
    for name in SCHEMA_NAMES:
        schema = _schema(name)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["properties"]["contract_version"] == {"const": "5"}
        assert schema["additionalProperties"] is False


def test_only_three_agent_contracts_exist() -> None:
    assert sorted(
        p.name for p in (ROOT / "contracts" / "agent").glob("*.json")
    ) == sorted(SCHEMA_NAMES)


def test_interpretation_uses_exactly_nine_closed_discriminated_act_branches() -> None:
    """Changing the model action vocabulary requires a deliberate schema revision."""
    schema = _schema("interpretation-schema.json")
    branches = schema["$defs"]["act"]["oneOf"]

    assert [branch["properties"]["kind"]["const"] for branch in branches] == [
        "create_radar",
        "set_filter",
        "clear_filter",
        "express_desire",
        "revise_desire",
        "withdraw_desire",
        "record_feedback",
        "query",
        "unsupported_request",
    ]
    assert all(branch["additionalProperties"] is False for branch in branches)


def test_interpretation_wire_contract_leaves_provenance_and_versions_to_code() -> None:
    schema = _schema("interpretation-schema.json")

    assert "model_version" not in schema["properties"]
    assert "prompt_version" not in schema["properties"]
    assert all(
        "evidence_text" in branch["properties"]
        and "evidence_spans" not in branch["properties"]
        for branch in schema["$defs"]["act"]["oneOf"]
    )


def test_express_desire_without_raw_text_is_invalid() -> None:
    """A durable desire must retain the user's expressed wording."""
    schema = _schema("interpretation-schema.json")
    payload = _interpretation(_act("express_desire", subject_ref="subject:balcony"))

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


@pytest.mark.parametrize(
    "concept_link",
    [
        {"concept_ref": "balcon", "confidence": 0.9, "intensity": "medium"},
        {"concept_ref": "balcon", "confidence": 0.9, "polarity": "positive"},
        {
            "concept_ref": "balcon",
            "confidence": 0.9,
            "polarity": "neutral",
            "intensity": "medium",
        },
        {
            "concept_ref": "balcon",
            "confidence": 0.9,
            "polarity": "positive",
            "intensity": "urgent",
        },
    ],
)
def test_computable_concept_links_require_closed_semantic_judgment(
    concept_link: dict[str, object],
) -> None:
    """A link without closed judgment cannot deterministically rank a soft desire."""
    schema = _schema("interpretation-schema.json")
    payload = _interpretation(
        _act(
            "express_desire",
            raw_text="Quiero balcón",
            subject_ref="balcon",
            concept_links=[concept_link],
        )
    )

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(payload, schema)


def test_computable_concept_link_accepts_closed_semantic_judgment() -> None:
    schema = _schema("interpretation-schema.json")
    payload = _interpretation(
        _act(
            "express_desire",
            raw_text="Quiero balcón",
            subject_ref="balcon",
            concept_links=[
                {
                    "concept_ref": "balcon",
                    "confidence": 0.9,
                    "polarity": "positive",
                    "intensity": "high",
                }
            ],
        )
    )

    jsonschema.validate(payload, schema)


def test_revision_without_target_is_valid_for_policy_clarification() -> None:
    schema = _schema("interpretation-schema.json")
    payload = _interpretation(
        _act(
            "revise_desire",
            raw_text="Cambiá ese deseo",
            concept_links=[],
        )
    )

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
    schema = _schema("interpretation-schema.json")

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
    schema = _schema("interpretation-schema.json")

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_interpretation(act), schema)


@pytest.mark.parametrize(
    ("filter_key", "json_value"),
    [
        ("budget_max", 1200.0),
        ("min_rooms", 2),
        ("zones", ["palermo", "belgrano"]),
    ],
)
def test_filter_schema_accepts_the_published_typed_values(
    filter_key: str, json_value: object
) -> None:
    """Set-filter payloads must share the closed value surface."""
    schema = _schema("interpretation-schema.json")

    jsonschema.validate(
        _interpretation(
            _act(
                "set_filter",
                filter_key=filter_key,
                value=json_value,
            )
        ),
        schema,
    )


@pytest.mark.parametrize(
    ("filter_key", "json_value"),
    [
        ("zones", {"not": "a zone list"}),
        ("min_rooms", [2]),
        ("budget_max", [1200]),
    ],
)
def test_filter_schema_rejects_key_value_type_mismatches(
    filter_key: str, json_value: object
) -> None:
    """A mismatched filter shape would create an untyped mutation proposal."""
    schema = _schema("interpretation-schema.json")

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            _interpretation(
                _act("set_filter", filter_key=filter_key, value=json_value)
            ),
            schema,
        )
