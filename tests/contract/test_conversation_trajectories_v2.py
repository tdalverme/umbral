"""Conformance of the v2 conversation-trajectory schema and release gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import jsonschema  # type: ignore[import-untyped]
import pytest

ROOT = Path(__file__).resolve().parents[2]
MANDATORY_INVARIANTS = [
    "final_state_matches_expected",
    "no_unconfirmed_material_effect",
    "forbidden_bindings_are_non_computable",
    "no_wrong_target_mutation",
]


def _load_json(relative_path: str) -> dict[str, Any]:
    return cast(
        dict[str, Any], json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
    )


def _dataset_with_invariants(invariants: list[str]) -> dict[str, Any]:
    return {
        "contract_version": "2",
        "registry_version": "conversation-trajectories-v2",
        "cases": [
            {
                "id": "critical-invariant-case",
                "family": "context_continuity",
                "initial_state": {},
                "turns": [
                    {
                        "user": "Quiero un depto luminoso",
                        "expected_acts": ["create_radar", "express_preference"],
                        "expected_effects": ["radar.created"],
                        "forbidden": [],
                    }
                ],
                "final_state": {"active_subjects": ["luminosidad"]},
                "invariants": invariants,
            }
        ],
    }


def test_trajectory_schema_accepts_declared_state_evolution() -> None:
    """Dropping durable snapshots or forbidden outcomes would hide regressions."""
    schema = _load_json(
        "contracts/agent-evals/v2/conversation-trajectories-v2.schema.json"
    )
    dataset = {
        "contract_version": "2",
        "registry_version": "conversation-trajectories-v2",
        "cases": [
            {
                "id": "reported-zone-loop",
                "family": "context_continuity",
                "initial_state": {"profiles": [], "session": {"profile_id": None}},
                "turns": [
                    {
                        "user": "Quiero un depto luminoso",
                        "expected_acts": ["create_radar", "express_preference"],
                        "expected_effects": [
                            "radar.created",
                            "preference.remembered",
                        ],
                        "forbidden": ["ask_zone_before_persist"],
                    }
                ],
                "final_state": {"zones": [], "active_subjects": ["luminosidad"]},
                "invariants": [
                    *MANDATORY_INVARIANTS,
                    "no_repeated_answered_question",
                ],
            }
        ],
    }

    jsonschema.validate(dataset, schema)


def test_trajectory_schema_rejects_case_without_critical_invariant() -> None:
    """An invariant-free case cannot contribute to a 100% critical gate."""
    schema = _load_json(
        "contracts/agent-evals/v2/conversation-trajectories-v2.schema.json"
    )
    dataset = {
        "contract_version": "2",
        "registry_version": "conversation-trajectories-v2",
        "cases": [
            {
                "id": "non-evaluable-case",
                "family": "context_continuity",
                "initial_state": {},
                "turns": [
                    {
                        "user": "Quiero un depto luminoso",
                        "expected_acts": ["create_radar", "express_preference"],
                        "expected_effects": ["radar.created"],
                        "forbidden": [],
                    }
                ],
                "final_state": {"active_subjects": ["luminosidad"]},
                "invariants": [],
            }
        ],
    }

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(dataset, schema)


def test_trajectory_schema_accepts_executable_invariant_for_each_category() -> None:
    """Omitting a critical category would make the 100% gate incomplete."""
    schema = _load_json(
        "contracts/agent-evals/v2/conversation-trajectories-v2.schema.json"
    )
    expected_categories = {
        "final_state_matches_expected": "state",
        "no_repeated_answered_question": "state",
        "no_unconfirmed_material_effect": "safety",
        "forbidden_bindings_are_non_computable": "equity",
        "no_wrong_target_mutation": "mutation",
    }
    registry = schema["x-invariant-registry"]
    declared_ids = set(
        schema["$defs"]["case"]["properties"]["invariants"]["items"]["enum"]
    )

    assert declared_ids == set(registry)
    assert schema["x-mandatory-invariant-ids"] == MANDATORY_INVARIANTS
    assert {
        invariant_id: registry[invariant_id]["category"]
        for invariant_id in expected_categories
    } == expected_categories
    assert all(
        registry[invariant_id]["pass_condition"] for invariant_id in declared_ids
    )
    assert all(registry[invariant_id]["evaluator_id"] for invariant_id in declared_ids)
    evidence_sources = schema["x-evidence-source-registry"]
    assert all(
        source_id in evidence_sources
        for invariant_id in declared_ids
        for source_id in registry[invariant_id]["evidence_sources"]
    )
    for invariant_id in expected_categories:
        invariants = list(MANDATORY_INVARIANTS)
        if invariant_id not in invariants:
            invariants.append(invariant_id)
        jsonschema.validate(_dataset_with_invariants(invariants), schema)


def test_trajectory_schema_rejects_unknown_invariant_id() -> None:
    """A typo or prose-only invariant must not bypass the executable registry."""
    schema = _load_json(
        "contracts/agent-evals/v2/conversation-trajectories-v2.schema.json"
    )

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            _dataset_with_invariants([*MANDATORY_INVARIANTS, "made_up_invariant"]),
            schema,
        )


@pytest.mark.parametrize("omitted_id", MANDATORY_INVARIANTS)
def test_trajectory_schema_rejects_omitted_mandatory_invariant(
    omitted_id: str,
) -> None:
    """Every acceptance case must exercise all four critical categories."""
    schema = _load_json(
        "contracts/agent-evals/v2/conversation-trajectories-v2.schema.json"
    )
    invariants = [item for item in MANDATORY_INVARIANTS if item != omitted_id]

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_dataset_with_invariants(invariants), schema)


def test_trajectory_schema_rejects_duplicate_invariant_id() -> None:
    """A repeated ID must not inflate critical invariant coverage."""
    schema = _load_json(
        "contracts/agent-evals/v2/conversation-trajectories-v2.schema.json"
    )

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            _dataset_with_invariants(
                [*MANDATORY_INVARIANTS, MANDATORY_INVARIANTS[0]]
            ),
            schema,
        )


def test_release_gate_is_strict() -> None:
    """Relaxing any gate could release a trajectory suite with critical harm."""
    gate = _load_json("contracts/agent-evals/v2/release-gate-v2.json")

    assert gate["contract_version"] == "2"
    assert gate["critical_invariants"] == 1.0
    assert gate["trajectory_success"] == 0.95
    assert gate["minimum_family_success"] == 0.90
    assert gate["wrong_target_mutations"] == 0
