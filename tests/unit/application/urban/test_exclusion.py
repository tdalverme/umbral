"""US1: listings without precise coordinates are excluded; the preference is missing."""

from __future__ import annotations

from uuid import uuid4

from tests.fakes.urban import utcnow

from umbral.application.urban.observations import observations_for_signal

_CID = uuid4()
_EXTRACTION_ID = uuid4()
_CONTRACT_ID = uuid4()
_SNAPSHOT_ID = uuid4()


def test_no_signal_reports_missing_not_a_mean_value() -> None:
    observations = observations_for_signal(
        listing_id=uuid4(),
        signals=[],
        concepts={"proximidad_cafes": "cafe_lifestyle"},
        contract_version_id=_CONTRACT_ID,
        extraction_version_id=_EXTRACTION_ID,
        snapshot_id=_SNAPSHOT_ID,
        created_at=utcnow(),
        correlation_id=_CID,
    )

    obs = observations[0]
    assert obs.state == "failed"
    assert obs.value is None
    assert obs.score == 0.0
    assert obs.confidence == 0.0
    assert obs.failure_code == "criteria.urban_unavailable"


def test_signal_ref_concept_keeps_identity_when_missing() -> None:
    observations = observations_for_signal(
        listing_id=uuid4(),
        signals=[],
        concepts={"proximidad_cafes": "cafe_lifestyle"},
        contract_version_id=_CONTRACT_ID,
        extraction_version_id=_EXTRACTION_ID,
        snapshot_id=_SNAPSHOT_ID,
        created_at=utcnow(),
        correlation_id=_CID,
    )

    assert observations[0].concept_key == "proximidad_cafes"
    assert observations[0].matcher_type == "signal_score"
    assert observations[0].source == "urban"
