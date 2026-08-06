"""Shared conformance of the ImportSource adapters (file and fake)."""

from __future__ import annotations

from pathlib import Path

import pytest

from umbral.application.ingestion.contracts import BatchRejected, ParsedBatch
from umbral.infrastructure.sources.fake_source import FakeImportSource
from umbral.infrastructure.sources.file_source import FileImportSource

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures" / "imports"

FILE_SOURCE = FileImportSource()


def test_file_source_parses_json_and_csv_to_identical_payloads() -> None:
    json_raw = (FIXTURES / "reference-batch.json").read_bytes()
    csv_raw = (FIXTURES / "reference-batch.csv").read_bytes()

    json_batch = FILE_SOURCE.read_batch(
        raw=json_raw, file_format="json", file_name="reference-batch.json"
    )
    csv_batch = FILE_SOURCE.read_batch(
        raw=csv_raw, file_format="csv", file_name="reference-batch.csv"
    )

    assert json_batch.total == 12
    assert csv_batch.total == 12
    json_payloads = [record.payload for record in json_batch.records]
    csv_payloads = [record.payload for record in csv_batch.records]
    for json_payload, csv_payload in zip(json_payloads, csv_payloads):
        for key, value in json_payload.items():
            if isinstance(value, list):
                assert csv_payload[key] == "|".join(str(item) for item in value)
            else:
                expected = "" if value is None else str(value)
                assert str(csv_payload[key] or "") == expected


def test_file_source_rejects_malformed_json_batch() -> None:
    with pytest.raises(BatchRejected) as error:
        FILE_SOURCE.read_batch(
            raw=b"{not json", file_format="json", file_name="broken.json"
        )
    assert error.value.code == "file.parse_error"


def test_file_source_rejects_non_object_json_batch() -> None:
    with pytest.raises(BatchRejected) as error:
        FILE_SOURCE.read_batch(
            raw=b'["a", "b"]', file_format="json", file_name="broken.json"
        )
    assert error.value.code == "file.parse_error"


def test_file_source_rejects_csv_without_header_or_rows() -> None:
    with pytest.raises(BatchRejected):
        FILE_SOURCE.read_batch(raw=b"", file_format="csv", file_name="broken.csv")
    with pytest.raises(BatchRejected):
        FILE_SOURCE.read_batch(raw=b"a,b,c", file_format="csv", file_name="broken.csv")


def test_file_source_reports_column_mismatch_as_parse_error() -> None:
    batch = FILE_SOURCE.read_batch(
        raw=b"external_id,price\n1,2\n3", file_format="csv", file_name="row.csv"
    )
    assert len(batch.records) == 1
    assert len(batch.parse_errors) == 1
    assert batch.parse_errors[0].code == "source.parse_error"
    assert batch.total == 2


def test_fake_source_returns_registered_batch() -> None:
    expected = FILE_SOURCE.read_batch(
        raw=(FIXTURES / "reference-batch.json").read_bytes(),
        file_format="json",
        file_name="reference-batch.json",
    )
    fake = FakeImportSource()
    fake.register("reference-batch.json", expected)

    result = fake.read_batch(
        raw=b"unused", file_format="json", file_name="reference-batch.json"
    )
    assert isinstance(result, ParsedBatch)
    assert result.total == expected.total


def test_fake_source_rejects_unknown_input() -> None:
    fake = FakeImportSource()
    with pytest.raises(BatchRejected):
        fake.read_batch(raw=b"x", file_format="json", file_name="unknown.json")
