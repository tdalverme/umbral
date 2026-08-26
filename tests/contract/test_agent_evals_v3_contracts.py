from __future__ import annotations

import json
from pathlib import Path

from umbral.application.agent_evals.v3.loader import load_dataset, load_policy
from umbral.application.agent_evals.v3.releases import load_releases

_ROOT = Path(__file__).parents[2]
_CONTRACTS = _ROOT / "contracts" / "agent-evals" / "v3"

_EXCLUDED_SOURCES = frozenset(
    {
        "conversation-001",
        "conversation-003",
        "conversation-007",
        "conversation-008",
        "conversation-009",
        "conversation-010",
        "conversation-011",
        "conversation-012",
        "conversation-019",
        "conversation-020",
        "conversation-022",
        "conversation-023",
        "conversation-024",
        "conversation-025",
        "conversation-026",
    }
)


def test_published_policy_and_releases_load() -> None:
    policy = load_policy(_CONTRACTS / "eval-policy-v3.json")
    releases = load_releases(_CONTRACTS / "graph-releases-v2.json")

    assert policy.registry_version == "eval-policy-v3"
    assert releases.releases[0].id == "graph-release-003"


def test_schema_is_strict_at_all_contract_levels() -> None:
    schema = json.loads(
        (_CONTRACTS / "conversation-trajectories-v3.schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert schema["additionalProperties"] is False
    for name in ("case", "turn", "script", "expectation", "predicate", "review"):
        assert schema["$defs"][name]["additionalProperties"] is False


def test_dataset_has_twenty_four_reviewed_cases_and_exact_holdouts() -> None:
    dataset = load_dataset(_CONTRACTS / "conversation-trajectories-v3.json")

    assert len(dataset.cases) == 24
    assert len({case.id for case in dataset.cases}) == 24
    holdouts = [case for case in dataset.cases if case.partition == "holdout"]
    assert len(holdouts) == 3
    assert all(case.suite != "safety" for case in holdouts)
    criticals = [case for case in dataset.cases if case.risk == "critical"]
    assert criticals
    assert all(case.suite in {"safety", "regression"} for case in criticals)
    assert all(case.review.reviewed_by for case in dataset.cases)
    assert all(case.review.reviewed_at for case in dataset.cases)
    assert all(case.review.rationale for case in dataset.cases)


def test_dataset_excludes_explanation_and_comparison_cases() -> None:
    dataset = load_dataset(_CONTRACTS / "conversation-trajectories-v3.json")

    for case in dataset.cases:
        assert case.id not in _EXCLUDED_SOURCES
    legacy_ids = {case.id for case in dataset.cases if case.id.startswith("legacy-")}
    assert legacy_ids == {
        "legacy-002",
        "legacy-004",
        "legacy-005",
        "legacy-006",
        "legacy-013",
        "legacy-014",
        "legacy-015",
        "legacy-016",
        "legacy-017",
        "legacy-018",
        "legacy-021",
    }


def test_historical_v1_and_v2_contracts_are_frozen() -> None:
    v1 = json.loads(
        (_ROOT / "contracts" / "agent-evals" / "v1" / "conversations-golden-v1.json")
        .read_text(encoding="utf-8")
    )
    v2 = json.loads(
        (
            _ROOT
            / "contracts"
            / "agent-evals"
            / "v2"
            / "conversation-trajectories-v2.json"
        ).read_text(encoding="utf-8")
    )

    assert v1["registry_version"] == "conversations-golden-v1"
    assert len(v1["cases"]) == 26
    assert v2["registry_version"] == "conversation-trajectories-v2"
    assert len(v2["cases"]) == 13


def test_v3_flow_reads_only_the_v3_dataset_path() -> None:
    source = (
        _ROOT / "src" / "umbral" / "infrastructure" / "agent_evals" / "v3_flow.py"
    ).read_text(encoding="utf-8")

    assert "conversation-trajectories-v3.json" in source
    assert "conversations-golden-v1.json" not in source
    assert "conversation-trajectories-v2.json" not in source
