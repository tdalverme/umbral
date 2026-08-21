# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Deterministic economic rules: precio_m2 and variacion_precio (FR-008/FR-009)."""

from __future__ import annotations

from umbral.application.criteria.rules import (
    run_precio_m2,
    run_variacion_precio,
)


def test_precio_m2_computes_price_per_area() -> None:
    outcome = run_precio_m2(
        {"price_value": 500000, "price_currency": "ARS", "surface_m2": 50}
    )
    assert outcome.value == 10000.0
    assert outcome.fragment == "precio 500000 ARS / superficie 50.0 m2"
    assert outcome.matched_on == ("price_value", "surface_m2")


def test_precio_m2_keeps_the_declared_currency() -> None:
    outcome = run_precio_m2(
        {"price_value": 1500, "price_currency": "USD", "surface_m2": 30}
    )
    assert outcome.value == 50.0
    assert "USD" in (outcome.fragment or "")


def test_precio_m2_is_unknown_without_surface_or_price() -> None:
    assert run_precio_m2(
        {"price_value": 500000, "price_currency": "ARS", "surface_m2": None}
    ).value is None
    assert run_precio_m2(
        {"price_value": 0, "price_currency": "ARS", "surface_m2": 50}
    ).value is None
    assert run_precio_m2({}).value is None


def test_variacion_precio_reports_a_drop_as_negative() -> None:
    outcome = run_variacion_precio(
        {
            "price_changes": [
                {"field": "price_value", "before": 500000, "after": 480000}
            ]
        }
    )
    assert outcome.value == -20000.0
    assert outcome.fragment == "precio 500000 -> 480000"
    assert outcome.matched_on == ("price_changes",)


def test_variacion_precio_reports_a_rise_as_positive() -> None:
    outcome = run_variacion_precio(
        {"price_changes": [{"field": "price_value", "before": 480000, "after": 500000}]}
    )
    assert outcome.value == 20000.0


def test_variacion_precio_is_unknown_without_changes() -> None:
    assert run_variacion_precio({}).value is None
    assert run_variacion_precio({"price_changes": []}).value is None
    assert run_variacion_precio(
        {"price_changes": [{"field": "price_value", "before": None, "after": 480000}]}
    ).value is None


def test_variacion_precio_skips_non_price_fields() -> None:
    outcome = run_variacion_precio(
        {
            "price_changes": [
                {"field": "amenities", "before": [], "after": ["cochera"]}
            ]
        }
    )
    assert outcome.value is None