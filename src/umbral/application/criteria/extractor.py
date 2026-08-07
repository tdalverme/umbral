"""Structured extraction port and pure orchestration helpers.

The domain never imports provider clients: infrastructure implements
:class:`StructuredExtractor`. The permitted input is a deterministic
projection of the normalized listing fields allowlisted by the extraction
contract; PII of users and raw HTML are structurally impossible to reach.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from umbral.application.criteria.contracts import ExtractionResult
from umbral.application.silver.contracts import NormalizedListing

_NO_EVIDENCE = "sin evidencia"


class StructuredExtractor(Protocol):
    """External managed provider with structured, schema-bounded output."""

    def extract(
        self,
        *,
        concept_key: str,
        permitted_input: Mapping[str, object],
        schema: Mapping[str, object],
        version: str,
    ) -> ExtractionResult: ...


@dataclass(frozen=True, slots=True)
class ExtractionContractSpec:
    """Parsed extraction-v1 contract: allowed fields and per-concept schemas."""

    contract_version: str
    registry_version: str
    allowed_input_fields: tuple[str, ...]
    forbidden_input_keys: tuple[str, ...]
    qualitative_max_attempts: int
    concepts: Mapping[str, Mapping[str, object]]


def parse_extraction_contract(data: Mapping[str, object]) -> ExtractionContractSpec:
    if data.get("contract_version") != "1":
        raise ValueError("unsupported extraction contract document version")
    allowed = data.get("allowed_input_fields")
    if not isinstance(allowed, list) or not all(
        isinstance(item, str) for item in allowed
    ):
        raise ValueError("allowed_input_fields are required")
    forbidden = data.get("forbidden_input_keys")
    if not isinstance(forbidden, list):
        raise ValueError("forbidden_input_keys are required")
    raw_concepts = data.get("concepts")
    if not isinstance(raw_concepts, Mapping):
        raise ValueError("concepts are required")
    raw_attempts = data.get("qualitative_max_attempts", 2)
    max_attempts = raw_attempts if isinstance(raw_attempts, int) else 2
    return ExtractionContractSpec(
        contract_version=str(data["contract_version"]),
        registry_version=str(data.get("registry_version", "extraction-v1")),
        allowed_input_fields=tuple(str(item) for item in allowed),
        forbidden_input_keys=tuple(str(item) for item in forbidden),
        qualitative_max_attempts=max_attempts,
        concepts={str(key): _as_mapping(value) for key, value in raw_concepts.items()},
    )


def build_permitted_input(
    listing: NormalizedListing,
    contract: ExtractionContractSpec,
    concept_key: str,
) -> Mapping[str, object]:
    """Deterministic projection of the allowed normalized fields."""

    concept = contract.concepts.get(concept_key)
    source = concept.get("source") if concept is not None else None
    raw_fields = concept.get("input_fields") if concept is not None else None
    if source == "model":
        fields = contract.allowed_input_fields
    elif isinstance(raw_fields, list):
        fields = tuple(str(item) for item in raw_fields)
    else:
        fields = contract.allowed_input_fields
    projection: dict[str, object] = {}
    for field in fields:
        value = getattr(listing, field, None)
        if value is not None:
            projection[field] = list(value) if isinstance(value, tuple) else value
    return projection


def validate_model_output(
    output: Mapping[str, object], schema: Mapping[str, object]
) -> tuple[bool, str | None]:
    """Hand-rolled schema conformance; returns (valid, error code)."""

    required = schema.get("required")
    if isinstance(required, list):
        for key in required:
            if key not in output:
                return False, f"missing_key:{key}"
    props = schema.get("properties")
    if not isinstance(props, Mapping):
        return False, "schema_invalid"
    for key, value in output.items():
        spec = props.get(key)
        if not isinstance(spec, Mapping):
            return False, f"unknown_key:{key}"
        value_type = spec.get("type")
        if value_type == "string":
            if not isinstance(value, str):
                return False, f"type_mismatch:{key}"
            enum = spec.get("enum")
            if isinstance(enum, list) and value not in enum:
                return False, f"enum_mismatch:{key}"
        elif value_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return False, f"type_mismatch:{key}"
            if spec.get("minimum") is not None and value < spec["minimum"]:
                return False, f"out_of_range:{key}"
            if spec.get("maximum") is not None and value > spec["maximum"]:
                return False, f"out_of_range:{key}"
    evidence = output.get("evidence")
    if not isinstance(evidence, str) or not evidence.strip():
        return False, "missing_evidence"
    return True, None


def evidence_fragment_text(output: Mapping[str, object]) -> str | None:
    evidence = output.get("evidence")
    return str(evidence) if isinstance(evidence, str) and evidence.strip() else None


def _as_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("expected an object mapping")
    return {str(key): item for key, item in value.items()}
