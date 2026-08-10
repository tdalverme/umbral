"""Unit tests for compiler rejection of non-computable concepts."""

from __future__ import annotations

import pytest

from umbral.application.criteria.compile import compile_criteria
from umbral.application.criteria.registry import ConceptSeed, is_computable
from umbral.infrastructure.criteria.contract_loader import (
    load_concepts_seed,
    load_matcher_types,
)


def _seed_by_key() -> dict[str, ConceptSeed]:
    seed = load_concepts_seed()
    return {concept.key: concept for concept in seed.concepts}


def test_forbidden_concept_is_exposed_as_non_computable() -> None:
    by_key = _seed_by_key()
    concept = by_key["barrio_seguro"]
    assert is_computable(concept.compute_policy) is False


def test_regular_concepts_are_computable_by_default() -> None:
    by_key = _seed_by_key()
    assert is_computable(by_key["balcon"].compute_policy) is True
    assert is_computable(by_key["ambientes"].compute_policy) is True


def test_compile_rejects_an_edit_referencing_a_non_computable_concept() -> None:
    by_key = _seed_by_key()
    with pytest.raises(Exception) as raised:
        compile_criteria(
            concepts=by_key,
            matcher_types=load_matcher_types(),
            facts=(),
            edits=(
                {
                    "concept_key": "barrio_seguro",
                    "matcher_type": "categorical",
                    "params": {"allowed_values": ["true"]},
                    "source_ref": "edit:manual",
                },
            ),
        )
    assert "concept_not_computable" in str(raised.value)


def test_compile_allows_an_edit_referencing_a_computable_concept() -> None:
    by_key = _seed_by_key()
    draft = compile_criteria(
        concepts=by_key,
        matcher_types=load_matcher_types(),
        facts=(),
        edits=(
            {
                "concept_key": "balcon",
                "matcher_type": "categorical",
                "params": {"allowed_values": ["true"]},
                "source_ref": "edit:manual",
            },
        ),
    )
    assert len(draft.criteria) == 1
