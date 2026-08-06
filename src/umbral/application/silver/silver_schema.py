"""Pure loader and normalizer for the published Silver schema contract.

The rule set is loaded from ``contracts/silver/v1/silver-schema.json`` by an
infrastructure loader and passed in as a :class:`SilverSchemaSpec`. Normalization
is deterministic, preserves original values and never invents data; geocoding is
a separate application seam and is not part of this module.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from umbral.application.ingestion.contracts import RawListingSnapshot
from umbral.application.silver.contracts import (
    CurrencyType,
    GeoPrecision,
    NormalizedFields,
    OperationType,
    PropertyType,
)

_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class RangeSpec:
    gt: float | None = None
    ge: float | None = None
    max: float | None = None
    max_items: int | None = None
    item_max_length: int | None = None
    max_length: int | None = None


@dataclass(frozen=True, slots=True)
class SilverSchemaSpec:
    contract_version: str
    normalizer_version: str
    enums: Mapping[str, tuple[str, ...]]
    ranges: Mapping[str, RangeSpec]
    errors: Mapping[str, str]
    precision_rules: Mapping[str, str]
    change_fields: Mapping[str, tuple[str, ...]]


def parse_silver_schema(data: Mapping[str, object]) -> SilverSchemaSpec:
    version = data.get("contract_version")
    if version != "1":
        raise ValueError("unsupported silver schema document version")
    normalizer_version = data.get("normalizer_version")
    if not isinstance(normalizer_version, str) or not normalizer_version:
        raise ValueError("normalizer_version is required")

    raw_enums = data.get("enums")
    if not isinstance(raw_enums, Mapping):
        raise ValueError("silver schema enums are required")
    enums = {
        str(name): tuple(str(item) for item in values)
        for name, values in raw_enums.items()
        if isinstance(values, list)
    }

    raw_ranges = data.get("ranges")
    ranges: dict[str, RangeSpec] = {}
    if isinstance(raw_ranges, Mapping):
        for name, raw in raw_ranges.items():
            if not isinstance(raw, Mapping):
                raise ValueError(f"silver range {name!r} must be an object")
            ranges[str(name)] = RangeSpec(
                gt=_optional_float(raw.get("gt")),
                ge=_optional_float(raw.get("ge")),
                max=_optional_float(raw.get("max")),
                max_items=_optional_int(raw.get("max_items")),
                item_max_length=_optional_int(raw.get("item_max_length")),
                max_length=_optional_int(raw.get("max_length")),
            )

    raw_errors = data.get("errors")
    errors: dict[str, str] = {}
    if isinstance(raw_errors, Mapping):
        errors = {str(name): str(detail) for name, detail in raw_errors.items()}

    raw_precision = data.get("precision_rules")
    precision_rules: dict[str, str] = {}
    if isinstance(raw_precision, Mapping):
        precision_rules = {
            str(name): str(value) for name, value in raw_precision.items()
        }

    raw_changes = data.get("change_fields")
    change_fields: dict[str, tuple[str, ...]] = {}
    if isinstance(raw_changes, Mapping):
        change_fields = {
            str(name): tuple(str(field) for field in values)
            for name, values in raw_changes.items()
            if isinstance(values, list)
        }

    return SilverSchemaSpec(
        contract_version=str(version),
        normalizer_version=str(normalizer_version),
        enums=enums,
        ranges=ranges,
        errors=errors,
        precision_rules=precision_rules,
        change_fields=change_fields,
    )


def normalize_snapshot(
    snapshot: RawListingSnapshot, spec: SilverSchemaSpec
) -> NormalizedFields:
    """Normalize one Bronze snapshot into normalized Silver fields."""
    payload = snapshot.payload
    errors: list[str] = []

    price_value = _as_number(payload.get("price"))
    price_currency = _as_currency(payload.get("currency"))
    if price_currency is None:
        errors.append("silver.currency_unsupported")
        price_currency = "ARS"
    if price_value is not None:
        price_range = spec.ranges.get("price_value")
        if price_range is not None and not _in_range(price_value, price_range):
            errors.append("silver.price_range")
            price_value = None
    if price_value is None:
        price_value = 0.0

    expenses_value = _as_number(payload.get("expenses"))
    if expenses_value is not None:
        expenses_range = spec.ranges.get("expenses_value")
        if expenses_range is not None and not _in_range(expenses_value, expenses_range):
            errors.append("silver.expenses_range")
            expenses_value = None
    expenses_currency = _as_currency(payload.get("expenses_currency")) or price_currency
    if (
        expenses_value is not None
        and _as_currency(payload.get("expenses_currency")) is None
    ):
        expenses_currency = price_currency

    assumptions: dict[str, object] = {}
    if (
        expenses_value is not None
        and expenses_currency is not None
        and expenses_currency != price_currency
    ):
        assumptions["expenses_currency_mismatch"] = True
        expenses_value = None
    total_cost = price_value
    if expenses_value is not None:
        total_cost = price_value + expenses_value

    surface = _as_number(payload.get("surface_m2"))
    if surface is not None and not _in_range(surface, spec.ranges.get("surface_m2")):
        errors.append("silver.surface_range")
        surface = None
    rooms = _as_int(payload.get("rooms"))
    if rooms is not None and not _in_int_range(rooms, spec.ranges.get("rooms")):
        errors.append("silver.rooms_range")
        rooms = None
    bedrooms = _as_int(payload.get("bedrooms"))
    if bedrooms is not None and not _in_int_range(
        bedrooms, spec.ranges.get("bedrooms")
    ):
        errors.append("silver.bedrooms_range")
        bedrooms = None
    floor = _as_int(payload.get("floor"))
    if floor is not None and not _in_int_range(floor, spec.ranges.get("floor")):
        errors.append("silver.floor_range")
        floor = None

    raw_amenities = payload.get("amenities")
    amenities: tuple[str, ...] = ()
    if isinstance(raw_amenities, list):
        amenity_range = spec.ranges.get("amenities")
        cleaned: list[str] = []
        for item in raw_amenities:
            if not isinstance(item, str):
                continue
            if amenity_range is not None and (
                amenity_range.max_length is not None
                and len(item) > amenity_range.max_length
            ):
                errors.append("silver.amenities_too_long")
                continue
            cleaned.append(item)
        amenities = tuple(cleaned[:100])

    description_text: str | None = None
    raw_description = payload.get("description")
    if isinstance(raw_description, str) and raw_description.strip():
        description_range = spec.ranges.get("description")
        if (
            description_range is not None
            and description_range.max_length is not None
            and len(raw_description) > description_range.max_length
        ):
            errors.append("silver.description_too_long")
        else:
            description_text = raw_description.strip()

    location_text = _as_string(payload.get("address_text"))
    if location_text is None:
        location_text = ""
    neighborhood = _as_string(payload.get("neighborhood"))
    if neighborhood is not None:
        neighborhood = neighborhood.strip()

    url: str | None = None
    raw_url = payload.get("url")
    if isinstance(raw_url, str) and raw_url.strip():
        if _URL_RE.fullmatch(raw_url.strip()):
            url = raw_url.strip()
        else:
            errors.append("silver.url_invalid")

    geometry, precision, geo_source = _assign_location(
        payload, spec, assumptions, errors
    )

    property_type = _as_property_type(payload.get("property_type"), spec)
    operation = _as_operation(payload.get("operation"), spec)

    return NormalizedFields(
        operation=operation,
        property_type=property_type,
        price_value=float(price_value),
        price_currency=price_currency,
        expenses_value=float(expenses_value) if expenses_value is not None else None,
        expenses_currency=expenses_currency,
        total_cost=float(total_cost),
        price_assumptions=assumptions,
        surface_m2=float(surface) if surface is not None else None,
        rooms=rooms,
        bedrooms=bedrooms,
        floor=floor,
        amenities=amenities,
        description_text=description_text,
        location_text=location_text,
        neighborhood=neighborhood,
        geo_precision=precision,
        geometry=geometry,
        geo_source=geo_source,
        url=url,
        normalization_errors=tuple(errors),
    )


def compare_listings(
    previous: object, current: object, spec: SilverSchemaSpec
) -> dict[str, tuple[str, object, object]]:
    """Return {field: (change_type, before, after)} for fields that differ."""
    changes: dict[str, tuple[str, object, object]] = {}
    for change_type, fields in spec.change_fields.items():
        for field in fields:
            before = getattr(previous, field)
            after = getattr(current, field)
            if before != after:
                changes[field] = (change_type, before, after)
    return changes


def _assign_location(
    payload: Mapping[str, object],
    spec: SilverSchemaSpec,
    assumptions: dict[str, object],
    errors: list[str],
) -> tuple[tuple[float, float] | None, GeoPrecision, str | None]:
    del assumptions, errors
    lat = _as_number(payload.get("latitude"))
    lng = _as_number(payload.get("longitude"))
    address = payload.get("address_text")
    has_address = isinstance(address, str) and bool(address.strip())
    has_neighborhood = isinstance(payload.get("neighborhood"), str) and bool(
        payload.get("neighborhood")
    )

    if lat is not None and lng is not None:
        geometry: tuple[float, float] | None = (float(lat), float(lng))
        if has_address:
            return geometry, "exact", None
        return geometry, "block", None
    if has_neighborhood:
        return None, "neighborhood", None
    if not has_address:
        return None, "unknown", None
    return None, "unknown", None


def _as_currency(value: object) -> CurrencyType | None:
    if isinstance(value, str) and value in {"ARS", "USD"}:
        return value  # type: ignore[return-value]
    return None


def _as_property_type(value: object, spec: SilverSchemaSpec) -> PropertyType:
    if isinstance(value, str) and value in spec.enums.get("property_type", ()):
        return value  # type: ignore[return-value]
    return "other"


def _as_operation(value: object, spec: SilverSchemaSpec) -> OperationType:
    if isinstance(value, str) and value in spec.enums.get("operation_type", ()):
        return value  # type: ignore[return-value]
    return "rental"


def _as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
    return None


def _as_string(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _in_range(value: float, range_spec: RangeSpec | None) -> bool:
    if range_spec is None:
        return True
    if range_spec.gt is not None and not value > range_spec.gt:
        return False
    if range_spec.ge is not None and not value >= range_spec.ge:
        return False
    if range_spec.max is not None and not value <= range_spec.max:
        return False
    return True


def _in_int_range(value: int, range_spec: RangeSpec | None) -> bool:
    return _in_range(float(value), range_spec)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("silver schema numeric bounds must be numbers")
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("silver schema integer bounds must be integers")
    return value
