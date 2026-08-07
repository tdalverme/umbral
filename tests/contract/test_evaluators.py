"""Conformance of the generic evaluators against golden cases."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from umbral.application.scoring.evaluators import (
    evaluate_categorical,
    evaluate_fixed_criterion,
    evaluate_geo_proximity,
    evaluate_numeric_range,
    evaluate_semantic_feature,
)

GOLDEN = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "scoring"
        / "evaluators-golden.json"
    ).read_text(encoding="utf-8")
)


def _assert_case(case: Mapping[str, object], result: object) -> None:
    expected = case["expected"]
    assert isinstance(expected, Mapping)
    assert isinstance(result, tuple) is False
    from umbral.application.scoring.evaluators import EvaluationResult

    assert isinstance(result, EvaluationResult)
    assert result.score == expected["score"], case["id"]
    assert result.confidence == expected["confidence"], case["id"]
    assert result.state == expected["state"], case["id"]


def test_numeric_range_golden_cases() -> None:
    for case in GOLDEN["numeric_range"]:
        params = case["input"]["params"]
        result = evaluate_numeric_range(case["input"]["value"], params)
        _assert_case(case, result)


def test_categorical_golden_cases() -> None:
    for case in GOLDEN["categorical"]:
        params = case["input"]["params"]
        result = evaluate_categorical(case["input"]["value"], params)
        _assert_case(case, result)


def test_semantic_feature_golden_cases() -> None:
    for case in GOLDEN["semantic_feature"]:
        params = case["input"]["params"]
        result = evaluate_semantic_feature(
            case["input"]["score"], case["input"]["confidence"], params
        )
        _assert_case(case, result)


def test_geo_proximity_golden_cases() -> None:
    for case in GOLDEN["geo_proximity"]:
        result = evaluate_geo_proximity(
            case["input"]["in_zone"], case["input"]["precision"]
        )
        _assert_case(case, result)


def test_fixed_criterion_golden_cases() -> None:
    for case in GOLDEN["fixed"]:
        input_data = case["input"]
        result = evaluate_fixed_criterion(
            input_data["kind"],
            budget_max=1000.0,
            total_cost=float(input_data.get("total_cost") or 0),
            min_rooms=int(input_data.get("min_rooms") or 0),
            rooms=input_data.get("rooms"),
            surface_min=input_data.get("surface_min"),
            surface_max=input_data.get("surface_max"),
            surface_m2=input_data.get("surface_m2"),
            zones=("palermo",),
            neighborhood=input_data.get("neighborhood", "palermo"),
            geo_precision=input_data.get("precision", "exact"),
        )
        _assert_case(case, result)


def test_unknown_never_counts_as_mismatch() -> None:
    for evaluator_call in (
        lambda: evaluate_numeric_range(None, {"min": 0, "max": 5}),
        lambda: evaluate_categorical(None, {"allowed_values": ["si"]}),
        lambda: evaluate_semantic_feature(None, None, {"threshold": 0.5}),
    ):
        result = evaluator_call()
        assert result.state == "unknown"
        assert result.confidence == 0.0
