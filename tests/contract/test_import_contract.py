"""Conformance of the controlled import contract and its validator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import pytest

from umbral.application.ingestion.contracts import ParsedBatch, ValidationResult
from umbral.application.ingestion.import_contract import (
    check_file,
    parse_contract,
    validate_record,
)
from umbral.infrastructure.ingestion.contract_loader import load_contract_v1
from umbral.infrastructure.sources.file_source import FileImportSource

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "contracts" / "import" / "v1" / "import-contract.json"
FIXTURES = ROOT / "tests" / "fixtures" / "imports"

CONTRACT = load_contract_v1(CONTRACT_PATH)
SOURCE = FileImportSource()


def _batch(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _validate_batch(
    raw: bytes, file_format: Literal["csv", "json"]
) -> tuple[ParsedBatch, list[ValidationResult]]:
    parsed = SOURCE.read_batch(raw=raw, file_format=file_format, file_name=file_format)
    results = [validate_record(record.payload, CONTRACT) for record in parsed.records]
    return parsed, results


def test_reference_json_yields_expected_acceptance_profile() -> None:
    parsed, results = _validate_batch(_batch("reference-batch.json"), "json")

    assert parsed.total == 12
    assert len(parsed.parse_errors) == 0
    valid = [result for result in results if result.valid]
    invalid = [result for result in results if not result.valid]
    assert len(valid) == 10
    assert len(invalid) == 2
    assert sum(result.missing_optional for result in valid) == 3

    codes = sorted({result.issues[0].code for result in invalid})
    assert codes == ["contract.enum_invalid", "contract.range_invalid"]


def test_reference_csv_yields_same_acceptance_profile() -> None:
    parsed, results = _validate_batch(_batch("reference-batch.csv"), "csv")

    assert parsed.total == 12
    valid = [result for result in results if result.valid]
    invalid = [result for result in results if not result.valid]
    assert len(valid) == 10
    assert len(invalid) == 2
    assert sum(result.missing_optional for result in valid) == 3


def test_required_field_missing_is_actionable() -> None:
    payload = {
        "operation": "rental",
        "property_type": "apartment",
        "price": 1000,
        "currency": "ARS",
        "address_text": "Direccion",
    }
    result = validate_record(payload, CONTRACT)
    assert not result.valid
    assert result.issues[0].code == "contract.required_field"
    assert result.issues[0].rule == "field.external_id"


def test_enum_and_range_violations_are_stable() -> None:
    bad_enum = validate_record(
        {
            "external_id": "x",
            "operation": "sale",
            "property_type": "apartment",
            "price": 1000,
            "currency": "ARS",
            "address_text": "a",
        },
        CONTRACT,
    )
    assert bad_enum.issues[0].code == "contract.enum_invalid"

    bad_range = validate_record(
        {
            "external_id": "x",
            "operation": "rental",
            "property_type": "apartment",
            "price": -1,
            "currency": "ARS",
            "address_text": "a",
        },
        CONTRACT,
    )
    assert bad_range.issues[0].code == "contract.range_invalid"


def test_type_and_url_violations() -> None:
    bad_type = validate_record(
        {
            "external_id": "x",
            "operation": "rental",
            "property_type": "apartment",
            "price": "caro",
            "currency": "ARS",
            "address_text": "a",
        },
        CONTRACT,
    )
    assert bad_type.issues[0].code == "contract.type_invalid"

    bad_url = validate_record(
        {
            "external_id": "x",
            "operation": "rental",
            "property_type": "apartment",
            "price": 1000,
            "currency": "ARS",
            "address_text": "a",
            "url": "ftp://nope",
        },
        CONTRACT,
    )
    assert bad_url.issues[0].code == "contract.url_invalid"


def test_numeric_strings_are_accepted_like_json_numbers() -> None:
    payload = {
        "external_id": "x",
        "operation": "rental",
        "property_type": "apartment",
        "price": "1500000",
        "currency": "ARS",
        "address_text": "a",
        "rooms": "2",
        "published_at": "2026-07-01T10:00:00-03:00",
    }
    assert validate_record(payload, CONTRACT).valid


def test_file_level_rules_reject_the_whole_batch() -> None:
    raw = _batch("reference-batch.json")
    assert (
        check_file(
            CONTRACT, raw=raw, file_format="json", declared_contract_version="1"
        ).valid
        is True
    )
    assert (
        check_file(
            CONTRACT, raw=raw, file_format="xml", declared_contract_version="1"
        ).code
        == "file.format_unsupported"
    )
    assert (
        check_file(
            CONTRACT, raw=raw, file_format="json", declared_contract_version="9"
        ).code
        == "file.version_unsupported"
    )
    assert (
        check_file(
            CONTRACT,
            raw=b"\xff\xfe\x00",
            file_format="json",
            declared_contract_version="1",
        ).code
        == "file.encoding_invalid"
    )
    assert (
        check_file(
            CONTRACT,
            raw=b"x" * (CONTRACT.file.max_file_size_bytes + 1),
            file_format="json",
            declared_contract_version="1",
        ).code
        == "file.size_exceeded"
    )


def test_contract_document_matches_the_published_json() -> None:
    published = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    parsed = parse_contract(published)
    assert parsed.contract_version == "1"
    external_id = parsed.field("external_id")
    assert external_id is not None
    assert external_id.required is True
    assert ("json", "csv") == tuple(parsed.file.formats)


def test_duplicate_record_is_not_an_error_but_a_repeat() -> None:
    payload = json.loads(
        (FIXTURES / "reference-batch.json").read_text(encoding="utf-8")
    )["records"][0]
    assert validate_record(payload, CONTRACT).valid is True


@pytest.mark.parametrize(
    "fixture,file_format,expected_total,expected_valid,expected_invalid",
    [
        ("reference-batch.json", "json", 12, 10, 2),
        ("reference-batch.csv", "csv", 12, 10, 2),
    ],
)
def test_reference_batches_across_formats(
    fixture: str,
    file_format: Literal["csv", "json"],
    expected_total: int,
    expected_valid: int,
    expected_invalid: int,
) -> None:
    parsed, results = _validate_batch(_batch(fixture), file_format)
    assert parsed.total == expected_total
    assert sum(result.valid for result in results) == expected_valid
    assert sum(not result.valid for result in results) == expected_invalid
