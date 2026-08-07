"""US4: structured extraction orchestration, schema validation, retry budget."""

from __future__ import annotations

from uuid import uuid4

import pytest
from tests.support.criteria import CriteriaTestContext

from umbral.application.criteria.contracts import (
    CriteriaPermanentError,
    ExtractionResult,
    RecomputeScope,
)
from umbral.application.criteria.extractor import (
    build_permitted_input,
    validate_model_output,
)
from umbral.infrastructure.criteria.contract_loader import load_extraction_contract
from umbral.infrastructure.criteria.extractors.fake import FakeStructuredExtractor

SCHEMA = {
    "type": "object",
    "required": ["value", "evidence", "confidence"],
    "properties": {
        "value": {"type": "string", "enum": ["baja", "media", "alta"]},
        "evidence": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


def test_permitted_input_never_includes_forbidden_keys() -> None:
    contract = load_extraction_contract()
    context = CriteriaTestContext()
    listing = context.add_listing(description_text="texto")
    projection = build_permitted_input(listing, contract, "luminosidad")
    assert "url" not in projection
    assert "snapshot_id" not in projection
    assert set(projection) <= set(contract.allowed_input_fields)


def test_validate_model_output_accepts_and_rejects_schemas() -> None:
    valid, error = validate_model_output(
        {"value": "media", "evidence": "luminoso", "confidence": 0.8}, SCHEMA
    )
    assert valid and error is None
    for bad in (
        {"value": "alto", "evidence": "x", "confidence": 0.8},
        {"value": "media", "evidence": "x", "confidence": 1.5},
        {"value": "media", "confidence": 0.8},
        {"value": "media", "evidence": "", "confidence": 0.8},
    ):
        assert validate_model_output(bad, SCHEMA)[0] is False


def test_model_extraction_persists_active_observation_with_lineage() -> None:
    context = CriteriaTestContext()
    context.seed_concepts()
    context.add_listing(description_text="departamento luminoso en Caballito")
    summary = context.service.process_extraction(
        RecomputeScope("concept", "luminosidad"), job_execution_id=uuid4()
    )
    assert summary["published"] == 1
    observation = next(
        item for item in context.observations.rows if item.concept_key == "luminosidad"
    )
    assert observation.source == "model"
    assert observation.state == "active"
    assert observation.value == "media"
    assert observation.evidence["fragment"] == "luminoso"
    assert observation.extraction_version_id is not None
    version = context.extraction_versions.get(observation.extraction_version_id)
    assert version is not None
    assert version.kind == "model"
    schema_version = context.extraction_versions.find(
        "schema", "luminosidad.schema", "v1"
    )
    assert schema_version is not None


class _FailingExtractor:
    def extract(self, **kwargs: object) -> ExtractionResult:
        return ExtractionResult(
            value={"value": "invalida", "evidence": "x", "confidence": 0.8},
            evidence_fragment="x",
            confidence=0.8,
        )


def test_invalid_model_output_fails_with_bounded_retries() -> None:
    context = CriteriaTestContext(extractor=_FailingExtractor())  # type: ignore[arg-type]
    context.seed_concepts()
    context.add_listing(description_text="departamento luminoso")
    summary = context.service.process_extraction(
        RecomputeScope("concept", "luminosidad"), job_execution_id=uuid4()
    )
    assert summary["failed"] == 1
    observation = next(
        item for item in context.observations.rows if item.concept_key == "luminosidad"
    )
    assert observation.state == "failed"
    assert observation.failure_code is not None
    assert "invalid_output" in observation.failure_code


def test_extractor_unavailable_is_a_permanent_error() -> None:
    context = CriteriaTestContext(default_extractor=False)
    context.seed_concepts()
    context.add_listing(description_text="departamento luminoso")
    with pytest.raises(CriteriaPermanentError):
        context.service.process_extraction(
            RecomputeScope("concept", "luminosidad"), job_execution_id=uuid4()
        )


def test_fake_extractor_records_only_permitted_input() -> None:
    fake = FakeStructuredExtractor(
        {
            "luminosidad": {
                "value": "alta",
                "evidence": "muy luminoso",
                "confidence": 0.9,
            }
        }
    )
    context = CriteriaTestContext(extractor=fake)
    context.seed_concepts()
    context.add_listing(description_text="muy luminoso", amenities=("terraza",))
    context.service.process_extraction(
        RecomputeScope("concept", "luminosidad"), job_execution_id=uuid4()
    )
    call = fake.calls[0]
    assert call["concept_key"] == "luminosidad"
    permitted = call["permitted_input"]
    assert isinstance(permitted, dict)
    assert "description_text" in permitted
    assert "url" not in permitted
