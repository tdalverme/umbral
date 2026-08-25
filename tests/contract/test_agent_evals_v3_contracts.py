from __future__ import annotations

import json
from pathlib import Path

from umbral.application.agent_evals.v3.loader import load_policy
from umbral.application.agent_evals.v3.releases import load_releases


_ROOT = Path(__file__).parents[2]
_CONTRACTS = _ROOT / "contracts" / "agent-evals" / "v3"


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
