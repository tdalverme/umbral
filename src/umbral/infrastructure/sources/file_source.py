"""File adapter that reads controlled CSV/JSON batches into raw records.

The adapter returns raw records plus a report and never references Silver. A
batch that cannot be parsed as a whole raises :class:`BatchRejected` with an
actionable diagnostic.
"""

from __future__ import annotations

import csv
import io
import json

from umbral.application.ingestion.contracts import (
    BatchRejected,
    ImportFormat,
    ParsedBatch,
    ParsedError,
    ParsedRecord,
)
from umbral.application.ingestion.import_contract import canonical_bytes


class FileImportSource:
    def read_batch(
        self, *, raw: bytes, file_format: ImportFormat, file_name: str
    ) -> ParsedBatch:
        del file_name
        text = _decode_utf8(raw)
        if file_format == "json":
            return _parse_json(text)
        return _parse_csv(text)


def _decode_utf8(raw: bytes) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BatchRejected(
            "file.encoding_invalid", "content is not valid UTF-8"
        ) from error
    return text.lstrip("\ufeff")


def _parse_json(text: str) -> ParsedBatch:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise BatchRejected("file.parse_error", f"invalid JSON: {error.msg}") from error
    if not isinstance(data, dict):
        raise BatchRejected("file.parse_error", "JSON batch must be an object")
    records_value = data.get("records")
    if not isinstance(records_value, list):
        raise BatchRejected(
            "file.parse_error", "JSON batch must contain a 'records' list"
        )
    records: list[ParsedRecord] = []
    errors: list[ParsedError] = []
    for index, item in enumerate(records_value):
        if not isinstance(item, dict):
            errors.append(
                ParsedError(
                    index, "source.parse_error", f"record {index} is not an object"
                )
            )
            continue
        records.append(ParsedRecord(payload=item, raw_bytes=canonical_bytes(item)))
    return ParsedBatch(tuple(records), tuple(errors))


def _parse_csv(text: str) -> ParsedBatch:
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader]
    if not rows or not any(rows):
        raise BatchRejected("file.parse_error", "CSV batch has no rows")
    header = [cell.strip() for cell in rows[0]]
    if not header or any(not cell for cell in header):
        raise BatchRejected("file.parse_error", "CSV batch header is empty")
    if len(rows) < 2:
        raise BatchRejected("file.parse_error", "CSV batch has no data records")
    records: list[ParsedRecord] = []
    errors: list[ParsedError] = []
    for index, row in enumerate(rows[1:], start=1):
        if len(row) != len(header):
            errors.append(
                ParsedError(
                    index,
                    "source.parse_error",
                    f"record {index} has {len(row)} columns, expected {len(header)}",
                )
            )
            continue
        payload: dict[str, object] = {header[j]: row[j] for j in range(len(header))}
        records.append(
            ParsedRecord(payload=payload, raw_bytes=canonical_bytes(payload))
        )
    return ParsedBatch(tuple(records), tuple(errors))
