"""Conformance of criteria compilation with golden cases."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from tests.fixtures.criteria import golden
from umbral.application.criteria.compile import compile_criteria
from umbral.application.criteria.contracts import (
    CriteriaValidationError,
    PreferenceFact,
    SoftToHardRequiresConfirmation,
)
from umbral.infrastructure.criteria.contract_loader import (
    load_concepts_seed,
    load_matcher_types,
)

SEED = load_concepts_seed()
MATCHER_TYPES = load_matcher_types()
BY_KEY = {seed.key: seed for seed in SEED.concepts}

PROFILE_ID = UUID("11111111-1111-1111-1111-111111111111")


def _fact(concept_key: str, weight: float = 0.8) -> PreferenceFact:
    return PreferenceFact(
        fact_id=uuid4(),
        profile_id=PROFILE_ID,
        concept_key=concept_key,
        value="true",
        weight=weight,
        polarity="positive",
        confidence=0.9,
        fact_source="harness",
        state="active",
        superseded_by=None,
        created_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        correlation_id=uuid4(),
    )


def test_golden_ordered_criteria_with_warnings() -> None:
    case = next(
        item
        for item in golden.compilations_golden()["cases"]
        if "ordered" in item["scenario"]
    )
    draft = compile_criteria(
        concepts=BY_KEY,
        matcher_types=MATCHER_TYPES,
        facts=(_fact("balcon"),),
        edits=tuple(case["edits"]),
    )
    assert len(draft.criteria) == case["expected_criteria_count"]
    assert draft.criteria[0].concept_key == "balcon"
    assert any("semantic_memory" in warning for warning in draft.warnings)


def test_facts_are_compiled_as_soft_criteria_ordered_by_weight() -> None:
    draft = compile_criteria(
        concepts=BY_KEY,
        matcher_types=MATCHER_TYPES,
        facts=(_fact("balcon", 0.5), _fact("tipo_cocina", 0.9)),
        edits=(),
    )
    keys = [criterion.concept_key for criterion in draft.criteria]
    assert keys == ["tipo_cocina", "balcon"]
    assert all(criterion.soft_to_hard is False for criterion in draft.criteria)
    assert draft.criteria[0].source_ref.startswith("fact:")


def test_soft_to_hard_without_confirmation_is_rejected() -> None:
    case = next(
        item
        for item in golden.compilations_golden()["cases"]
        if "rejected" in item["scenario"]
    )
    try:
        compile_criteria(
            concepts=BY_KEY,
            matcher_types=MATCHER_TYPES,
            facts=(),
            edits=tuple(case["edits"]),
            confirmations=(),
        )
    except SoftToHardRequiresConfirmation:
        pass
    else:
        raise AssertionError("expected soft->hard rejection without confirmation")


def test_soft_to_hard_with_confirmation_compiles() -> None:
    draft = compile_criteria(
        concepts=BY_KEY,
        matcher_types=MATCHER_TYPES,
        facts=(),
        edits=(
            {
                "concept_key": "balcon",
                "matcher_type": "categorical",
                "params": {"allowed_values": ["true"]},
                "source_ref": "fact:x",
                "soft_to_hard": True,
            },
        ),
        confirmations=("balcon",),
    )
    assert draft.criteria[0].soft_to_hard is True
    assert draft.confirmations == ("balcon",)


def test_invalid_matcher_params_are_rejected() -> None:
    try:
        compile_criteria(
            concepts=BY_KEY,
            matcher_types=MATCHER_TYPES,
            facts=(),
            edits=(
                {
                    "concept_key": "balcon",
                    "matcher_type": "categorical",
                    "params": {"radius_m": 10},
                    "source_ref": "fact:x",
                    "soft_to_hard": False,
                },
            ),
        )
    except CriteriaValidationError:
        pass
    else:
        raise AssertionError("expected invalid param rejection")


def test_unknown_concept_is_rejected() -> None:
    try:
        compile_criteria(
            concepts=BY_KEY,
            matcher_types=MATCHER_TYPES,
            facts=(),
            edits=(
                {
                    "concept_key": "no_existe",
                    "matcher_type": "categorical",
                    "params": {},
                    "source_ref": "fact:x",
                    "soft_to_hard": False,
                },
            ),
        )
    except CriteriaValidationError as error:
        assert any("concept_not_found" in code for code in error.error_codes)
    else:
        raise AssertionError("expected unknown concept rejection")
