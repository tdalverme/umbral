"""Pure loader and per-record validator for the published import contract.

The rule set is loaded from ``contracts/import/v1/import-contract.json`` by an
infrastructure loader and passed in as a :class:`ContractSpec`. Validation is
deterministic, format-agnostic (JSON values and CSV string scalars both work)
and never touches storage or the network.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from umbral.application.ingestion.contracts import ValidationIssue, ValidationResult

FieldType = Literal[
    "string",
    "number",
    "integer",
    "enum",
    "array_string",
    "array_url",
    "url",
    "datetime",
]

_URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
_LIST_SEPARATOR = "|"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    required: bool
    value_type: FieldType
    values: tuple[str, ...] = ()
    min_length: int | None = None
    max_length: int | None = None
    gt: float | None = None
    ge: float | None = None
    max: float | None = None
    max_items: int | None = None
    item_max_length: int | None = None

    def rule(self) -> str:
        return f"field.{self.name}"


@dataclass(frozen=True, slots=True)
class FileSpec:
    formats: tuple[str, ...]
    encodings: tuple[str, ...]
    max_file_size_bytes: int
    max_records: int


@dataclass(frozen=True, slots=True)
class ContractSpec:
    contract_version: str
    file: FileSpec
    fields: tuple[FieldSpec, ...]

    def field(self, name: str) -> FieldSpec | None:
        for spec in self.fields:
            if spec.name == name:
                return spec
        return None


@dataclass(frozen=True, slots=True)
class FileCheck:
    valid: bool
    code: str | None
    detail: str | None


def parse_contract(data: Mapping[str, object]) -> ContractSpec:
    """Build the immutable contract from the published JSON document."""
    version = data.get("contract_version")
    if version != "1":
        raise ValueError("unsupported contract document version")
    file_data = data.get("file")
    if not isinstance(file_data, Mapping):
        raise ValueError("contract file rules are required")
    raw_fields = data.get("fields")
    if not isinstance(raw_fields, Mapping):
        raise ValueError("contract fields are required")

    formats = _string_tuple(file_data.get("formats"), "file.formats")
    encodings = _string_tuple(file_data.get("encodings"), "file.encodings")
    max_size = _positive_int(
        file_data.get("max_file_size_bytes"), "max_file_size_bytes"
    )
    max_records = _positive_int(file_data.get("max_records"), "max_records")

    fields: list[FieldSpec] = []
    for name, raw in raw_fields.items():
        if not isinstance(raw, Mapping):
            raise ValueError(f"contract field {name!r} must be an object")
        required = bool(raw.get("required", False))
        value_type = raw.get("type")
        if value_type not in {
            "string",
            "number",
            "integer",
            "enum",
            "array_string",
            "array_url",
            "url",
            "datetime",
        }:
            raise ValueError(f"contract field {name!r} has an unknown type")
        values = (
            tuple(str(item) for item in raw.get("values", ()))
            if raw.get("values")
            else ()
        )
        fields.append(
            FieldSpec(
                name=name,
                required=required,
                value_type=value_type,
                values=values,
                min_length=_optional_int(raw.get("min_length")),
                max_length=_optional_int(raw.get("max_length")),
                gt=_optional_float(raw.get("gt")),
                ge=_optional_float(raw.get("ge")),
                max=_optional_float(raw.get("max")),
                max_items=_optional_int(raw.get("max_items")),
                item_max_length=_optional_int(raw.get("item_max_length")),
            )
        )
    return ContractSpec(
        contract_version=str(version),
        file=FileSpec(
            formats=formats,
            encodings=encodings,
            max_file_size_bytes=max_size,
            max_records=max_records,
        ),
        fields=tuple(fields),
    )


def check_file(
    spec: ContractSpec,
    *,
    raw: bytes,
    file_format: str,
    declared_contract_version: str,
) -> FileCheck:
    """File-level rules; a violation rejects the whole batch."""
    if declared_contract_version != spec.contract_version:
        return FileCheck(
            False,
            "file.version_unsupported",
            f"unsupported contract version {declared_contract_version!r}",
        )
    if file_format not in spec.file.formats:
        return FileCheck(
            False, "file.format_unsupported", f"format {file_format!r} is not supported"
        )
    if not _is_utf8(raw):
        return FileCheck(False, "file.encoding_invalid", "content is not valid UTF-8")
    if len(raw) > spec.file.max_file_size_bytes:
        return FileCheck(
            False,
            "file.size_exceeded",
            f"file exceeds {spec.file.max_file_size_bytes} bytes",
        )
    return FileCheck(True, None, None)


def validate_record(
    payload: Mapping[str, object], spec: ContractSpec
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    missing = 0
    for field in spec.fields:
        value = payload.get(field.name)
        if _field_missing(field, value):
            if field.required:
                issues.append(
                    ValidationIssue(
                        "contract.required_field",
                        field.rule(),
                        f"required field {field.name!r} is missing",
                    )
                )
            else:
                missing += 1
            continue
        error = _validate_value(field, value)
        if error is not None:
            issues.append(error)
    return ValidationResult(
        valid=not issues, issues=tuple(issues), missing_optional=missing
    )


def count_missing_by_name(
    payloads: list[Mapping[str, object]], spec: ContractSpec
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for field in spec.fields:
        if field.required:
            continue
        for payload in payloads:
            if _field_missing(field, payload.get(field.name)):
                counts[field.name] = counts.get(field.name, 0) + 1
    return counts


def canonical_bytes(payload: Mapping[str, object]) -> bytes:
    """Deterministic, format-independent JSON bytes for integrity hashing."""
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def canonical_hash(payload: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def _validate_value(field: FieldSpec, value: object) -> ValidationIssue | None:
    try:
        if field.value_type == "string":
            return _validate_string(field, value)
        if field.value_type in {"number", "integer"}:
            return _validate_number(field, value)
        if field.value_type == "enum":
            return _validate_enum(field, value)
        if field.value_type == "url":
            return _validate_url(field, value)
        if field.value_type == "datetime":
            return _validate_datetime(field, value)
        if field.value_type in {"array_string", "array_url"}:
            return _validate_array(field, value)
    except (TypeError, ValueError, OverflowError):
        return ValidationIssue(
            "contract.type_invalid",
            field.rule(),
            f"field {field.name!r} has an invalid value",
        )
    return None


def _validate_string(field: FieldSpec, value: object) -> ValidationIssue | None:
    if not isinstance(value, str):
        return _type_issue(field)
    if field.min_length is not None and len(value) < field.min_length:
        return _range_issue(field, f"shorter than {field.min_length}")
    if field.max_length is not None and len(value) > field.max_length:
        return _range_issue(field, f"longer than {field.max_length}")
    return None


def _validate_number(field: FieldSpec, value: object) -> ValidationIssue | None:
    number = _as_number(value)
    if number is None or (
        field.value_type == "integer" and not float(number).is_integer()
    ):
        return _type_issue(field)
    if field.gt is not None and not number > field.gt:
        return _range_issue(field, f"must be greater than {field.gt}")
    if field.ge is not None and not number >= field.ge:
        return _range_issue(field, f"must be at least {field.ge}")
    if field.max is not None and not number <= field.max:
        return _range_issue(field, f"must be at most {field.max}")
    return None


def _validate_enum(field: FieldSpec, value: object) -> ValidationIssue | None:
    if not isinstance(value, str) or value not in field.values:
        return ValidationIssue(
            "contract.enum_invalid",
            field.rule(),
            f"field {field.name!r} has an unsupported value",
        )
    return None


def _validate_url(field: FieldSpec, value: object) -> ValidationIssue | None:
    if not isinstance(value, str) or not _URL_RE.fullmatch(value.strip()):
        return ValidationIssue(
            "contract.url_invalid",
            field.rule(),
            f"field {field.name!r} is not a valid http(s) URL",
        )
    return None


def _validate_datetime(field: FieldSpec, value: object) -> ValidationIssue | None:
    parsed = _as_datetime(value)
    if parsed is None:
        return _type_issue(field)
    return None


def _validate_array(field: FieldSpec, value: object) -> ValidationIssue | None:
    items = value if isinstance(value, list) else _split_list(value)
    if items is None:
        return _type_issue(field)
    if field.max_items is not None and len(items) > field.max_items:
        return _range_issue(field, f"has more than {field.max_items} items")
    for item in items:
        if not isinstance(item, str):
            return _type_issue(field)
        if field.value_type == "array_url" and not _URL_RE.fullmatch(item.strip()):
            return ValidationIssue(
                "contract.url_invalid",
                field.rule(),
                f"field {field.name!r} contains an invalid URL",
            )
        if field.item_max_length is not None and len(item) > field.item_max_length:
            return _range_issue(field, f"item longer than {field.item_max_length}")
    return None


def _as_number(value: object) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return None
    return None


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _split_list(value: object) -> list[str] | None:
    if not isinstance(value, str):
        return None
    return [item.strip() for item in value.split(_LIST_SEPARATOR) if item.strip()]


def _field_missing(field: FieldSpec, value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return field.value_type not in {"array_string", "array_url"}
    if isinstance(value, list) and value == []:
        return False
    return False


def _is_utf8(raw: bytes) -> bool:
    try:
        raw.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _type_issue(field: FieldSpec) -> ValidationIssue:
    return ValidationIssue(
        "contract.type_invalid",
        field.rule(),
        f"field {field.name!r} has an invalid type",
    )


def _range_issue(field: FieldSpec, detail: str) -> ValidationIssue:
    return ValidationIssue(
        "contract.range_invalid", field.rule(), f"field {field.name!r} {detail}"
    )


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must contain only strings")
    return tuple(str(item) for item in value)


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("contract numeric bounds must be integers")
    return value


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("contract numeric bounds must be numbers")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("contract numeric bounds must be finite")
    return number
