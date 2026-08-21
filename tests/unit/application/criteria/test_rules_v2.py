"""US1 deterministic rules for the housing catalog (dormitorios/mascotas/amenities)."""

from __future__ import annotations

from umbral.application.criteria.rules import (
    run_ascensor,
    run_cochera,
    run_dormitorios,
    run_mascotas,
    run_piscina,
)


def test_dormitorios_prefers_structured_bedrooms_field() -> None:
    outcome = run_dormitorios({"bedrooms": 2, "description_text": "3 ambientes"})
    assert outcome.value == 2
    assert outcome.matched_on == ()


def test_dormitorios_falls_back_to_free_text() -> None:
    outcome = run_dormitorios(
        {"bedrooms": None, "description_text": "2 dormitorios depto"}
    )
    assert outcome.value == 2
    assert "description_text" in outcome.matched_on
    assert outcome.fragment is not None


def test_dormitorios_missing_stays_unknown() -> None:
    outcome = run_dormitorios(
        {"bedrooms": None, "description_text": "Departamento luminoso"}
    )
    assert outcome.value is None
    assert outcome.fragment is None


def test_mascotas_positive_wording() -> None:
    outcome = run_mascotas(
        {"description_text": "Se aceptan mascotas.", "amenities": []}
    )
    assert outcome.value == "true"
    assert outcome.fragment is not None


def test_mascotas_negative_wording() -> None:
    outcome = run_mascotas(
        {"description_text": "No se aceptan mascotas.", "amenities": []}
    )
    assert outcome.value == "false"


def test_mascotas_from_amenity() -> None:
    outcome = run_mascotas({"description_text": "", "amenities": ["acepta mascotas"]})
    assert outcome.value == "true"
    assert "amenities" in outcome.matched_on


def test_mascotas_ambiguous_stays_unknown() -> None:
    outcome = run_mascotas(
        {"description_text": "Departamento luminoso.", "amenities": []}
    )
    assert outcome.value is None


def test_ascensor_from_amenity_list() -> None:
    outcome = run_ascensor({"amenities": ["ascensor"], "description_text": ""})
    assert outcome.value == "true"
    assert outcome.matched_on == ("amenities",)


def test_ascensor_explicit_negative_on_text() -> None:
    outcome = run_ascensor({"amenities": [], "description_text": "Sin ascensor."})
    assert outcome.value == "false"


def test_ascensor_bare_mention_stays_unknown() -> None:
    outcome = run_ascensor(
        {"amenities": [], "description_text": "Sin informacion de ascensor."}
    )
    assert outcome.value is None


def test_cochera_from_amenity_and_negative() -> None:
    positive = run_cochera({"amenities": ["cochera"], "description_text": ""})
    assert positive.value == "true"
    negative = run_cochera({"amenities": [], "description_text": "Sin cochera."})
    assert negative.value == "false"
    unknown = run_cochera({"amenities": [], "description_text": "Departamento."})
    assert unknown.value is None


def test_cochera_prefers_structured_parking_spaces() -> None:
    positive = run_cochera(
        {"parking_spaces": 1, "amenities": [], "description_text": "Departamento."}
    )
    assert positive.value == "true"
    assert positive.matched_on == ("parking_spaces",)

    negative = run_cochera(
        {"parking_spaces": 0, "amenities": ["cochera"], "description_text": ""}
    )
    assert negative.value == "false"
    assert negative.matched_on == ("parking_spaces",)


def test_piscina_from_amenity_and_negative() -> None:
    positive = run_piscina({"amenities": ["piscina"], "description_text": ""})
    assert positive.value == "true"
    negative = run_piscina({"amenities": [], "description_text": "Sin pileta."})
    assert negative.value == "false"
    unknown = run_piscina({"amenities": [], "description_text": "Con parrilla."})
    assert unknown.value is None
