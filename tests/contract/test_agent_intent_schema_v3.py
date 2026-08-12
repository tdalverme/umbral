"""Intent schema v3 conformance (UM-H4-017, T014)."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.agent.intent.contracts import (
    IntentContractInvalid,
    parse_intent_contract,
)
from umbral.infrastructure.agent.intent.contract_loader import load_intent_contract

ROOT = Path(__file__).resolve().parents[2]


def test_intent_contract_declares_five_intents_with_policy() -> None:
    contract = load_intent_contract()
    assert contract.registry_version == "agent-intent-schema-v3"
    assert contract.schema_version == "intent-v3"
    names = {declaration.name for declaration in contract.intents}
    assert names == {
        "consulta",
        "refinamiento",
        "comparacion",
        "feedback",
        "fuera_de_alcance",
    }
    assert contract.allowed_tools_for("consulta") == (
        "get_search_profile",
        "find_matches",
        "explain_match",
        "get_listing_detail",
        "list_search_preferences",
        "search_urban_context",
    )
    assert contract.allowed_tools_for("refinamiento") == (
        "propose_search_profile_update",
        "propose_search_preference_update",
        "propose_search_preference_removal",
    )
    assert contract.allowed_tools_for("fuera_de_alcance") == ()
    assert contract.known_intents() == names


def test_intent_contract_declares_high_impact_keys() -> None:
    contract = load_intent_contract()
    assert set(contract.high_impact_keys) == {
        "budget",
        "zona",
        "hard_filters",
        "radio",
    }


def test_intent_contract_rejects_unknown_registry() -> None:
    data = json.loads(
        (ROOT / "contracts" / "agent" / "v3" / "intent-schema-v3.json").read_text(
            encoding="utf-8"
        )
    )
    data["registry_version"] = "nope"
    try:
        parse_intent_contract(data)
    except IntentContractInvalid:
        return
    raise AssertionError("expected IntentContractInvalid")


def test_intent_contract_output_schema_is_present() -> None:
    contract = load_intent_contract()
    assert "intent" in contract.output_schema
    assert "parameters" in contract.output_schema
