"""Conformance of the Silver schema contract and its normalizer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.silver import load_records, snapshot_from_payload
from umbral.application.silver.silver_schema import (
    normalize_snapshot,
    parse_silver_schema,
)
from umbral.infrastructure.silver.contract_loader import load_silver_schema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "contracts" / "silver" / "v2" / "silver-schema.json"

SCHEMA = load_silver_schema(SCHEMA_PATH)


def _first(records: list[dict[str, object]], external_id: str) -> dict[str, object]:
    return next(record for record in records if record["external_id"] == external_id)


def test_contract_document_matches_the_published_json() -> None:
    published = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    parsed = parse_silver_schema(published)
    assert parsed.contract_version == "2"
    assert parsed.normalizer_version == "silver-schema-v2"
    assert "price_value" in parsed.ranges
    assert "exact" in parsed.enums["geo_precision"]


def test_reference_valid_records_normalize_without_conversion() -> None:
    records = load_records("reference-batch.json")
    valid = [r for r in records if _is_valid(r)]
    for record in valid:
        fields = normalize_snapshot(snapshot_from_payload(record), SCHEMA)
        assert fields.normalization_errors == ()
        price = _as_float(record.get("price"))
        assert fields.price_value == price
        assert fields.price_currency == record.get("currency")
        expenses = record.get("expenses")
        if expenses is not None:
            assert fields.expenses_value == _as_float(expenses)
            assert fields.total_cost == price + _as_float(expenses)
        else:
            assert fields.expenses_value is None
            assert fields.total_cost == price


def test_price_and_currency_are_preserved_verbatim() -> None:
    record = _first(load_records("reference-batch.json"), "sil-0009")
    fields = normalize_snapshot(snapshot_from_payload(record), SCHEMA)
    assert fields.price_currency == "USD"
    assert fields.price_value == 1100000.0


def test_location_precision_follows_granularity() -> None:
    records = load_records("reference-batch.json")
    with_coords = _first(records, "sil-0001")
    assert (
        normalize_snapshot(snapshot_from_payload(with_coords), SCHEMA).geo_precision
        == "exact"
    )

    neighborhood_only = _first(records, "sil-0004")
    assert (
        normalize_snapshot(
            snapshot_from_payload(neighborhood_only), SCHEMA
        ).geo_precision
        == "neighborhood"
    )

    address_only = _first(records, "sil-0005")
    fields = normalize_snapshot(snapshot_from_payload(address_only), SCHEMA)
    assert fields.geo_precision == "unknown"
    assert fields.geometry is None


def test_no_invented_coordinates_or_addresses() -> None:
    record = _first(load_records("reference-batch.json"), "sil-0004")
    fields = normalize_snapshot(snapshot_from_payload(record), SCHEMA)
    assert fields.geometry is None
    assert fields.location_text == record["address_text"]


def test_new_listing_attributes_normalize_with_source_values() -> None:
    record = {
        "external_id": "attributes",
        "operation": "rental",
        "property_type": "apartment",
        "price": 1000,
        "currency": "USD",
        "address_text": "Avenida del Libertador 100",
        "title": "Departamento en Puerto Madero",
        "surface_m2": 82,
        "surface_covered_m2": 72,
        "rooms": 2,
        "bedrooms": 1,
        "bathrooms": 1,
        "toilettes": 1,
        "parking_spaces": 1,
        "age_years": 3,
        "disposition": "Frente",
        "orientation": "SE",
        "amenities": ["Gimnasio", "Parrilla"],
        "description": "Departamento luminoso.",
        "media_urls": ["https://img.example.com/one.jpg"],
    }

    fields = normalize_snapshot(
        snapshot_from_payload(record, contract_version="2"), SCHEMA
    )

    assert fields.title_text == "Departamento en Puerto Madero"
    assert fields.surface_covered_m2 == 72.0
    assert fields.bathrooms == 1.0
    assert fields.toilettes == 1.0
    assert fields.parking_spaces == 1.0
    assert fields.age_years == 3.0
    assert fields.disposition == "Frente"
    assert fields.orientation == "SE"
    assert fields.media_urls == ("https://img.example.com/one.jpg",)


def test_new_listing_attributes_reject_invalid_values_without_inventing() -> None:
    record = {
        "external_id": "invalid-attributes",
        "operation": "rental",
        "property_type": "apartment",
        "price": 1000,
        "currency": "USD",
        "address_text": "Avenida del Libertador 100",
        "surface_covered_m2": 0,
        "bathrooms": -1,
        "toilettes": 101,
        "parking_spaces": 101,
        "age_years": -1,
        "disposition": "x" * 101,
        "orientation": "y" * 101,
        "media_urls": ["ftp://invalid.example.com/image.jpg"],
    }

    fields = normalize_snapshot(
        snapshot_from_payload(record, contract_version="2"), SCHEMA
    )
    codes = set(fields.normalization_errors)

    assert "silver.surface_covered_range" in codes
    assert "silver.bathrooms_range" in codes
    assert "silver.toilettes_range" in codes
    assert "silver.parking_spaces_range" in codes
    assert "silver.age_years_range" in codes
    assert "silver.disposition_too_long" in codes
    assert "silver.orientation_too_long" in codes
    assert "silver.media_url_invalid" in codes
    assert fields.surface_covered_m2 is None
    assert fields.bathrooms is None
    assert fields.toilettes is None
    assert fields.parking_spaces is None
    assert fields.age_years is None
    assert fields.disposition is None
    assert fields.orientation is None
    assert fields.media_urls == ()


def test_new_listing_attributes_are_change_tracked() -> None:
    base = {
        "external_id": "changing-attributes",
        "operation": "rental",
        "property_type": "apartment",
        "price": 1000,
        "currency": "USD",
        "address_text": "Avenida del Libertador 100",
        "title": "Departamento",
        "surface_covered_m2": 70,
        "bathrooms": 1,
        "media_urls": ["https://img.example.com/one.jpg"],
    }
    changed = dict(base)
    changed["surface_covered_m2"] = 72
    changed["bathrooms"] = 2
    changed["title"] = "Departamento amplio"
    changed["media_urls"] = ["https://img.example.com/two.jpg"]

    previous = normalize_snapshot(
        snapshot_from_payload(base, contract_version="2"), SCHEMA
    )
    current = normalize_snapshot(
        snapshot_from_payload(changed, contract_version="2"), SCHEMA
    )
    diffs = _compare(previous, current)

    assert diffs["surface_covered_m2"][0] == "attribute"
    assert diffs["bathrooms"][0] == "attribute"
    assert diffs["title_text"][0] == "text"
    assert diffs["media_urls"][0] == "text"


def test_out_of_range_attributes_are_recorded_not_coerced() -> None:
    record = {
        "external_id": "bad",
        "operation": "rental",
        "property_type": "apartment",
        "price": 100000,
        "currency": "ARS",
        "address_text": "Av. Corrientes 2400",
        "neighborhood": "San Nicolas",
        "surface_m2": 999999999,
        "rooms": 999,
        "bedrooms": -1,
        "floor": 5000,
        "description": "x" * 30000,
        "url": "ftp://nope",
    }
    fields = normalize_snapshot(snapshot_from_payload(record), SCHEMA)
    codes = set(fields.normalization_errors)
    assert "silver.surface_range" in codes
    assert "silver.rooms_range" in codes
    assert "silver.bedrooms_range" in codes
    assert "silver.floor_range" in codes
    assert "silver.description_too_long" in codes
    assert "silver.url_invalid" in codes
    assert fields.surface_m2 is None
    assert fields.rooms is None
    assert fields.url is None


def test_unsupported_currency_is_recorded_not_converted() -> None:
    record = {
        "external_id": "bad-currency",
        "operation": "rental",
        "property_type": "apartment",
        "price": 100000,
        "currency": "EUR",
        "address_text": "Av. Corrientes 2400",
    }
    fields = normalize_snapshot(snapshot_from_payload(record), SCHEMA)
    assert "silver.currency_unsupported" in fields.normalization_errors
    assert fields.price_value == 100000.0


def test_compare_listings_detects_price_and_text_changes_only() -> None:
    records = load_records("reference-batch.json")
    v1 = normalize_snapshot(snapshot_from_payload(_first(records, "sil-0001")), SCHEMA)
    changed = dict(_first(records, "sil-0001"))
    changed["price"] = 900000
    v2 = normalize_snapshot(snapshot_from_payload(changed), SCHEMA)
    diffs = _compare(v1, v2)
    assert set(diffs) == {"price_value", "total_cost"}
    assert diffs["price_value"][0] == "price"


def test_status_field_has_no_change_fields_in_v2() -> None:
    assert SCHEMA.change_fields["status"] == ()


def test_v2_schema_declares_listing_attributes() -> None:
    path = ROOT / "contracts" / "silver" / "v2" / "silver-schema.json"
    published = json.loads(path.read_text(encoding="utf-8"))
    parsed = parse_silver_schema(published)

    assert parsed.contract_version == "2"
    assert parsed.normalizer_version == "silver-schema-v2"
    for field in (
        "title_text",
        "surface_covered_m2",
        "bathrooms",
        "toilettes",
        "parking_spaces",
        "age_years",
        "disposition",
        "orientation",
        "media_urls",
    ):
        assert field in parsed.ranges


def test_v1_silver_schema_is_not_accepted_anymore() -> None:
    data = json.loads(
        (ROOT / "contracts" / "silver" / "v1" / "silver-schema.json").read_text(
            encoding="utf-8"
        )
    )
    with pytest.raises(ValueError, match="unsupported silver schema document version"):
        parse_silver_schema(data)


def _is_valid(record: dict[str, object]) -> bool:
    return str(record.get("external_id", "")).startswith("sil-000")


def _as_float(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise AssertionError(f"expected numeric price, got {value!r}")


def _compare(
    previous: object, current: object
) -> dict[str, tuple[str, object, object]]:
    from umbral.application.silver.silver_schema import compare_listings

    return compare_listings(previous, current, SCHEMA)
