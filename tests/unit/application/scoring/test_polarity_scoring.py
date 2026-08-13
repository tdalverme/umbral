# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Polarity-aware qualitative scoring (fase 2 hallazgo 1).

The fact polarity now reaches the compiled criterion params and the
evaluators: semantic features invert the degree for negative preferences and
categorical criteria match the preferred value (or invert the domain for
negative binary preferences).
"""

from __future__ import annotations

from umbral.application.criteria.service import _qualitative_score
from umbral.application.scoring.evaluators import (
    evaluate_categorical,
    evaluate_semantic_feature,
)

_LUMINOSIDAD_SCHEMA = {
    "properties": {
        "value": {
            "enum": ["baja", "media", "alta"],
        }
    }
}


def test_qualitative_score_is_positional_over_the_enum() -> None:
    assert _qualitative_score("baja", _LUMINOSIDAD_SCHEMA) == 0.0
    assert _qualitative_score("media", _LUMINOSIDAD_SCHEMA) == 0.5
    assert _qualitative_score("alta", _LUMINOSIDAD_SCHEMA) == 1.0
    assert _qualitative_score("otro", _LUMINOSIDAD_SCHEMA) == 0.0
    assert _qualitative_score(None, _LUMINOSIDAD_SCHEMA) == 0.0


def test_semantic_positive_matches_high_observed_score() -> None:
    result = evaluate_semantic_feature(
        0.9, 0.8, {"threshold": 0.5, "polarity": "positive"}
    )
    assert result.state == "match"
    assert result.score == 0.9
    result = evaluate_semantic_feature(
        0.2, 0.8, {"threshold": 0.5, "polarity": "positive"}
    )
    assert result.state == "mismatch"


def test_semantic_negative_inverts_the_degree() -> None:
    low = evaluate_semantic_feature(
        0.2, 0.8, {"threshold": 0.5, "polarity": "negative"}
    )
    assert low.state == "match"
    assert low.score == 0.8
    high = evaluate_semantic_feature(
        0.9, 0.8, {"threshold": 0.5, "polarity": "negative"}
    )
    assert high.state == "mismatch"
    assert high.score == 0.1


def test_semantic_defaults_to_positive_without_polarity() -> None:
    result = evaluate_semantic_feature(0.9, 0.8, {"threshold": 0.5})
    assert result.state == "match"


def test_categorical_negative_inverts_domain_match() -> None:
    params = {"allowed_values": ["true", "false"], "polarity": "negative"}
    absent = evaluate_categorical("false", params)
    assert absent.state == "match"
    present = evaluate_categorical("true", params)
    assert present.state == "mismatch"


def test_categorical_preferred_value_matches_only_that_value() -> None:
    params = {
        "allowed_values": ["none", "separada", "integrada", "otra"],
        "polarity": "positive",
        "preferred_value": "separada",
    }
    assert evaluate_categorical("separada", params).state == "match"
    assert evaluate_categorical("integrada", params).state == "mismatch"


def test_categorical_negative_preferred_value_inverts() -> None:
    params = {
        "allowed_values": ["none", "separada", "integrada", "otra"],
        "polarity": "negative",
        "preferred_value": "separada",
    }
    assert evaluate_categorical("integrada", params).state == "match"
    assert evaluate_categorical("separada", params).state == "mismatch"
