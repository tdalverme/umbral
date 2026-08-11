"""Conformance of the ambiguity allowances sidecar contract."""

from __future__ import annotations

import json
from pathlib import Path

from umbral.application.agent_evals.allowances import load_allowances
from umbral.application.agent_evals.golden import load_golden_dataset

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts" / "agent-evals" / "v1"
GOLDEN_PATH = CONTRACTS / "conversations-golden-v1.json"
ALLOWANCES_PATH = CONTRACTS / "ambiguity-allowances-v1.json"


def test_allowances_document_is_valid_json() -> None:
    raw = json.loads(ALLOWANCES_PATH.read_text(encoding="utf-8"))
    assert raw["registry_version"] == "ambiguity-allowances-v1"
    assert isinstance(raw["allowances"], list)


def test_allowance_cases_exist_in_the_golden_dataset() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    known = frozenset(case.id for case in dataset.cases)
    allowances = load_allowances(ALLOWANCES_PATH, known_case_ids=known)
    assert allowances


def test_every_allowance_has_product_justification() -> None:
    allowances = load_allowances(ALLOWANCES_PATH)
    for allowance in allowances.values():
        assert allowance.justification
        assert allowance.acceptable_outcomes
