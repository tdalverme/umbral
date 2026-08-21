"""Unit tests for the manual MercadoLibre import generator mapper."""

from __future__ import annotations

import pytest

from umbral.ops.import_ml import map_item


def _item(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "MLA1234567890",
        "title": "Departamento en Palermo 2 ambientes",
        "category_id": "MLA1461",
        "price": 450000.0,
        "currency_id": "ARS",
        "permalink": "https://articulo.mercadolibre.com.ar/MLA-1234567890",
        "date_created": "2026-08-01T10:00:00.000-03:00",
        "address": {
            "state_id": "TUxBUEN",
            "state_name": "Buenos Aires",
            "city_id": "TUxBQCBW",
            "city_name": "Capital Federal",
            "neighborhood": {"id": "TUxBQUFQRU1v", "name": "Palermo"},
            "address_line": "Av. Santa Fe 3000",
        },
        "location": {"latitude": -34.588, "longitude": -58.409},
        "attributes": [
            {
                "id": "PROPERTY_TYPE",
                "name": "Tipo de propiedad",
                "value_name": "Departamento",
            },
            {"id": "ROOMS", "name": "Ambientes", "value_name": "3"},
            {"id": "BEDROOMS", "name": "Dormitorios", "value_name": "2"},
            {"id": "COVERED_AREA", "name": "Cubiertos", "value_name": "65 m²"},
            {"id": "TOTAL_AREA", "name": "Totales", "value_name": "80 m²"},
            {"id": "BATHROOMS", "name": "Baños", "value_name": "2"},
            {"id": "TOILETS", "name": "Toilettes", "value_name": "1"},
            {"id": "PARKING_LOTS", "name": "Cocheras", "value_name": "1"},
            {"id": "AGE", "name": "Antigüedad", "value_name": "10 años"},
            {"id": "DISPOSITION", "name": "Disposición", "value_name": "Frente"},
            {"id": "ORIENTATION", "name": "Orientación", "value_name": "Norte"},
            {
                "id": "EXPENSES",
                "name": "Expensas",
                "values": [
                    {"id": "", "name": "ARS 10000", "struct": {"number": 10000}}
                ],
            },
        ],
        "pictures": [
            {"id": "1", "url": "http://http2.mlstatic.com/1.jpg", "secure_url": "https://http2.mlstatic.com/1.jpg"}
        ],
    }
    base.update(overrides)
    return base


def test_map_item_full_record() -> None:
    record = map_item(_item())
    assert record is not None
    assert record["external_id"] == "MLA1234567890"
    assert record["operation"] == "rental"
    assert record["property_type"] == "apartment"
    assert record["price"] == 450000.0
    assert record["currency"] == "ARS"
    assert record["address_text"] == "Av. Santa Fe 3000"
    assert record["title"] == "Departamento en Palermo 2 ambientes"
    assert record["neighborhood"] == "Palermo"
    assert record["latitude"] == -34.588
    assert record["longitude"] == -58.409
    assert record["surface_m2"] == 80.0
    assert record["surface_covered_m2"] == 65.0
    assert record["rooms"] == 3
    assert record["bedrooms"] == 2
    assert record["bathrooms"] == 2.0
    assert record["toilettes"] == 1.0
    assert record["parking_spaces"] == 1.0
    assert record["age_years"] == 10.0
    assert record["disposition"] == "Frente"
    assert record["orientation"] == "Norte"
    assert record["expenses"] == 10000.0
    assert record["url"] == "https://articulo.mercadolibre.com.ar/MLA-1234567890"
    assert record["media_urls"] == ["https://http2.mlstatic.com/1.jpg"]
    assert record["published_at"] == "2026-08-01T10:00:00-03:00"


def test_map_item_infer_property_type_from_spanish_values() -> None:
    for value, expected in [
        ("Casa", "house"),
        ("Monoambiente", "studio"),
        ("Habitación en alquiler", "room"),
        ("Oficina en alquiler", "commercial"),
        ("PH", "house"),
        ("Departamento en venta", "apartment"),
    ]:
        record = map_item(
            _item(attributes=[{"id": "PROPERTY_TYPE", "value_name": value}])
        )
        assert record is not None
        assert record["property_type"] == expected, value


def test_map_item_unknown_property_type_defaults_to_other() -> None:
    record = map_item(
        _item(attributes=[{"id": "PROPERTY_TYPE", "value_name": "Lote de lujo"}])
    )
    assert record is not None
    assert record["property_type"] == "other"


@pytest.mark.parametrize(
    "overrides",
    [
        {"id": None},
        {"price": None},
        {"currency_id": "BRL"},
        {"address": {}},
        {"address": None},
    ],
)
def test_map_item_skips_when_required_field_missing(
    overrides: dict[str, object],
) -> None:
    assert map_item(_item(**overrides)) is None


def test_map_item_optional_fields_absent() -> None:
    record = map_item(
        _item(
            attributes=[],
            pictures=[],
            date_created=None,
            location={},
            permalink=None,
            address={
                "city_name": "Capital Federal",
                "state_name": "Buenos Aires",
            },
        )
    )
    assert record is not None
    assert record["address_text"] == "Capital Federal, Buenos Aires"
    assert "neighborhood" not in record
    assert "latitude" not in record
    assert "surface_m2" not in record
    assert "rooms" not in record
    assert "media_urls" not in record
    assert "url" not in record
    assert "published_at" not in record
    assert "expenses" not in record
