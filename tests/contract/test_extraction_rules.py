"""Conformance of the deterministic extraction rules with golden cases."""

from __future__ import annotations

from tests.fixtures.criteria import golden
from umbral.application.criteria.rules import RULE_RUNNERS, rule_version, run_rule


def test_rule_runners_exist_for_the_seed_rule_concepts() -> None:
    assert set(RULE_RUNNERS) == {"balcon", "ambientes", "piso", "tipo_cocina"}
    for concept in RULE_RUNNERS:
        assert rule_version(concept).startswith(f"{concept}.rule-")


def test_golden_cases_produce_the_expected_values_and_evidence() -> None:
    for case in golden.rules_golden()["cases"]:
        outcome = run_rule(case["concept"], dict(case["input"]))
        expected = case["expected"]
        assert outcome.value == expected["value"], case
        assert (outcome.fragment is not None) == expected["has_evidence"], case


def test_same_input_twice_produces_identical_outcomes() -> None:
    case = golden.rules_golden()["cases"][0]
    first = run_rule(case["concept"], dict(case["input"]))
    second = run_rule(case["concept"], dict(case["input"]))
    assert first == second


def test_missing_signal_declares_no_evidence_instead_of_inventing() -> None:
    outcome = run_rule(
        "balcon", {"description_text": "Piso luminoso en Caballito.", "amenities": []}
    )
    assert outcome.value is None
    assert outcome.fragment is None
    assert outcome.matched_on == ()


def test_unknown_rule_concept_is_rejected() -> None:
    try:
        run_rule("no_existe", {})
    except KeyError:
        pass
    else:
        raise AssertionError("expected KeyError for unknown rule")
