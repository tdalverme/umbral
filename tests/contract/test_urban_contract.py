"""Conformance of the declarative urban contract document."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from umbral.application.urban.contract import (
    UrbanContract,
    UrbanContractInvalid,
    load_urban_contract,
    parse_urban_contract,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "contracts" / "urban" / "v1" / "urban-contract-v1.json"


def _load() -> dict[str, Any]:
    data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return cast(dict[str, Any], data)


def _contract() -> UrbanContract:
    return load_urban_contract(CONTRACT_PATH)


def test_contract_document_matches_the_published_json() -> None:
    parsed = load_urban_contract(CONTRACT_PATH)

    assert parsed.contract_version == "urban-contract-v1"
    assert parsed.source.name == "geofabrik"
    assert parsed.source.license == "odbl-1.0"
    assert "OpenStreetMap" in parsed.source.attribution
    assert parsed.distance_radius_m == 1200
    assert len(parsed.tags_mapping) == 12
    assert len(parsed.linear_tags_mapping) == 4
    assert parsed.normalization.min_sample_per_barrio == 10
    assert parsed.normalization.fallback_scope == "caba"
    assert parsed.confidence.missing_penalty == 0.3
    assert parsed.missing.confidence == 0.0


def test_mapping_covers_density_and_infrastructure_categories() -> None:
    contract = _contract()
    categories = {mapping.category for mapping in contract.tags_mapping}
    required = {
        "cafe",
        "supermarket",
        "pharmacy",
        "nightlife",
        "subway_station",
        "green_space",
        "shopping_mall",
    }
    assert required <= categories
    linear = {mapping.category for mapping in contract.linear_tags_mapping}
    assert {"major_road", "highway", "railway", "subway_line"} <= linear


def test_signals_declare_modes_and_formulas() -> None:
    contract = _contract()
    base = {signal.name: signal for signal in contract.signals}
    assert base["cafe_lifestyle"].kind == "density"
    assert base["cafe_lifestyle"].normalized_by == "barrio"
    assert base["green_access"].kind == "distance"
    assert base["green_access"].normalized_by == "absolute"
    assert base["transit_access"].normalized_by == "barrio"
    assert base["road_noise"].normalized_by == "absolute"

    # Every base formula references only declared primitives.
    for signal in contract.signals:
        for term in signal.formula:
            assert term.primitive_ref is not None
            category, _metric = term.primitive_ref.split(".", 1)
            assert category in contract.primitive_names()


def test_composite_signals_reference_base_or_prior_composites() -> None:
    contract = _contract()
    composite_by_name = {signal.name: signal for signal in contract.composite_signals}
    assert set(composite_by_name) == {"walkability", "noise_risk", "residential_calm"}
    # residential_calm combines noise_risk (a composite) and commercial_intensity.
    residential = composite_by_name["residential_calm"]
    assert "noise_risk" in residential.signal_refs
    assert "commercial_intensity" in residential.signal_refs
    noise_risk = composite_by_name["noise_risk"]
    assert "nightlife_intensity" in noise_risk.signal_refs


def test_confidence_is_derived_from_input_coverage() -> None:
    contract = _contract()
    assert contract.confidence.method == "weighted_input_coverage"
    assert 0 < contract.confidence.missing_penalty < 1


def test_missing_uses_a_global_default() -> None:
    contract = _contract()
    assert contract.missing.value is None
    assert contract.missing.confidence == 0.0


def test_invalid_weights_are_rejected() -> None:
    data = _load()
    walkability = next(
        signal
        for signal in data["composite_signals"]
        if signal["name"] == "walkability"
    )
    walkability["formula"]["terms"][0]["weight"] = 0.5  # now totals > 1.0
    with pytest.raises(UrbanContractInvalid):
        parse_urban_contract(data)


def test_unknown_primitive_reference_is_rejected() -> None:
    data = _load()
    cafe = next(
        signal for signal in data["signals"] if signal["name"] == "cafe_lifestyle"
    )
    cafe["formula"]["terms"][0]["primitive"] = "nonexistent.count_300m"
    with pytest.raises(UrbanContractInvalid):
        parse_urban_contract(data)


def test_source_attribution_is_required() -> None:
    data = _load()
    del data["source"]["attribution"]
    with pytest.raises(UrbanContractInvalid):
        parse_urban_contract(data)


def test_new_category_and_signal_parse_without_code_changes() -> None:
    data = _load()

    data["tags_mapping"].append(
        {
            "category": "gym",
            "osm_tags": [["leisure", "fitness_centre"], ["leisure", "sports_centre"]],
        }
    )
    data["primitives"]["gym"] = [
        {"name": "count_300m", "kind": "count", "radius_m": 300},
        {"name": "count_600m", "kind": "count", "radius_m": 600},
        {"name": "nearest_m", "kind": "nearest"},
    ]
    data["signals"].append(
        {
            "name": "gym_access",
            "kind": "density",
            "normalized_by": "barrio",
            "formula": {
                "terms": [
                    {
                        "primitive": "gym.count_300m",
                        "op": "count",
                        "target": 2,
                        "weight": 1.0,
                    }
                ]
            },
        }
    )

    parsed = parse_urban_contract(data)

    assert any(m.category == "gym" for m in parsed.tags_mapping)
    assert any(s.name == "gym_access" for s in parsed.signals)
    assert parsed.signal_by_name("gym_access") is not None
