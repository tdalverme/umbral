"""Contract-driven tool registry: lookup, argument validation and redaction."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Callable
from uuid import UUID

from umbral.agent.tools.contracts import (
    ToolArgsInvalid,
    ToolContractInvalid,
    ToolNotFound,
    ToolSpec,
)

SpecFactory = Callable[[], list[ToolSpec]]

_INPUT_KINDS = ("integer", "string", "boolean", "object", "array", "uuid", "datetime")
_NULLABLE_SUFFIX = "|null"


class ToolRegistry:
    """Exposes the published tools and enforces their common contract."""

    def __init__(self, spec_factory: SpecFactory) -> None:
        self._specs: list[ToolSpec] = list(spec_factory())
        self._by_name: dict[str, ToolSpec] = {spec.name: spec for spec in self._specs}
        if len(self._by_name) != len(self._specs):
            raise ToolContractInvalid("tool.duplicate")

    def names(self) -> list[str]:
        return [spec.name for spec in self._specs]

    def get(self, name: str) -> ToolSpec:
        spec = self._by_name.get(name)
        if spec is None:
            raise ToolNotFound()
        return spec

    def validate_args(self, spec: ToolSpec, args: Mapping[str, object]) -> None:
        expected = spec.input_schema
        for field, raw_kind in expected.items():
            if field not in args:
                raise ToolArgsInvalid(f"{spec.name}:{field}")
            kind = _kind_of(raw_kind)
            _validate_kind(field, kind, args[field])
            _validate_enum(field, raw_kind, args[field])
        unknown = set(args) - set(expected)
        if unknown:
            raise ToolArgsInvalid(f"{spec.name}:{sorted(unknown)[0]}")

    def apply_redaction(
        self, spec: ToolSpec, output: Mapping[str, object]
    ) -> Mapping[str, object]:
        limits = spec.output_limits
        max_items = _positive_int(limits.get("max_items"))
        forbidden = limits.get("forbidden_keys", [])
        if not isinstance(forbidden, list) or not all(
            isinstance(key, str) for key in forbidden
        ):
            raise ToolContractInvalid("tool.output_limits.forbidden_keys")
        forbidden_set = set(forbidden)
        return _redact_mapping(output, max_items, forbidden_set)


def _kind_of(value: object) -> object:
    """Extract the kind string from a plain or enriched input schema entry."""
    if isinstance(value, Mapping):
        kind = value.get("kind")
        if isinstance(kind, str):
            return kind
        return None
    return value


def _validate_kind(field: str, kind: object, value: object) -> None:
    if not isinstance(kind, str):
        raise ToolArgsInvalid(f"{field}:kind")
    nullable = kind.endswith(_NULLABLE_SUFFIX)
    base = kind[: -len(_NULLABLE_SUFFIX)] if nullable else kind
    if nullable and value is None:
        return
    if base == "integer":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif base == "string":
        ok = isinstance(value, str)
    elif base == "boolean":
        ok = isinstance(value, bool)
    elif base == "object":
        ok = isinstance(value, Mapping)
    elif base == "array":
        ok = isinstance(value, list)
    elif base == "uuid":
        ok = isinstance(value, str) and _is_uuid(value)
    elif base == "datetime":
        ok = isinstance(value, str)
    else:
        ok = False
    if not ok:
        raise ToolArgsInvalid(f"{field}:{base}")


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _validate_enum(field: str, raw_kind: object, value: object) -> None:
    enum = raw_kind.get("enum") if isinstance(raw_kind, Mapping) else None
    if not isinstance(enum, list) or not enum:
        return
    if value is None:
        return
    if isinstance(value, list):
        if not all(item in enum for item in value):
            raise ToolArgsInvalid(f"{field}:enum")
        return
    if value not in enum:
        raise ToolArgsInvalid(f"{field}:enum")


def _redact(
    value: object, max_items: int | None, forbidden: set[str], _path: str = ""
) -> object:
    if isinstance(value, Mapping):
        return {
            key: _redact(item, max_items, forbidden, f"{_path}.{key}")
            for key, item in value.items()
            if key not in forbidden
        }
    if isinstance(value, list):
        items = [_redact(item, max_items, forbidden, _path) for item in value]
        if max_items is not None and len(items) > max_items:
            items = items[:max_items]
        return items
    return value


def _redact_mapping(
    output: Mapping[str, object], max_items: int | None, forbidden: set[str]
) -> Mapping[str, object]:
    return {
        key: _redact(item, max_items, forbidden, f".{key}")
        for key, item in output.items()
        if key not in forbidden
    }


def _positive_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    raise ToolContractInvalid("tool.output_limits.max_items")
