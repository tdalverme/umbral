"""Extraction goldens gate the publication of a concept (fase 3, US5)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from umbral.application.criteria.goldens import (
    ExtractionGoldenInvalid,
    evaluate_extraction_golden,
)
from umbral.application.criteria.rules import run_rule
from umbral.infrastructure.criteria.contract_loader import (
    load_extraction_contract,
    load_extraction_goldens,
)


def test_goldens_load_and_reference_published_concepts() -> None:
    goldens = load_extraction_goldens()
    contract = load_extraction_contract()
    assert "balcon" in goldens
    assert "moderno" in goldens
    assert "proximidad_cafes" in goldens
    for concept_key, golden in goldens.items():
        assert concept_key in contract.concepts, (
            f"golden {concept_key} without extraction contract entry"
        )
        assert golden.cases


def test_rule_golden_runs_the_real_rule() -> None:
    golden = load_extraction_goldens()["balcon"]
    evaluation = evaluate_extraction_golden(
        golden,
        extract=lambda case_input: run_rule("balcon", case_input).value,
    )
    assert evaluation.accuracy == 1.0
    assert evaluation.passed


def test_urban_golden_enforces_min_count() -> None:
    golden = load_extraction_goldens()["proximidad_cafes"]

    def extract(case_input: Mapping[str, Any]) -> int:
        return int(case_input.get("signal_count", 0))

    evaluation = evaluate_extraction_golden(golden, extract)
    assert evaluation.accuracy == 1.0
    assert evaluation.passed


def test_golden_fails_when_extraction_regresses() -> None:
    golden = load_extraction_goldens()["balcon"]
    evaluation = evaluate_extraction_golden(
        golden,
        extract=lambda _case_input: None,
    )
    assert not evaluation.passed
    assert evaluation.detail


def test_golden_document_rejects_structural_violations() -> None:
    import json
    from pathlib import Path

    data = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "contracts"
            / "criteria"
            / "v1"
            / "extraction-goldens-v1.json"
        ).read_text(encoding="utf-8")
    )
    bad = dict(data, registry_version="nope")
    try:
        from umbral.application.criteria.goldens import parse_extraction_goldens

        parse_extraction_goldens(bad)
    except ExtractionGoldenInvalid:
        return
    raise AssertionError("malformed golden document must be rejected")
