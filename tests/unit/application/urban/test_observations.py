"""US1: urban observations carry score/confidence/evidence or explicit missing."""

from __future__ import annotations

from uuid import uuid4

from tests.fakes.urban import utcnow

from umbral.application.urban.observations import observations_for_signal

_CID = uuid4()
_EXTRACTION_ID = uuid4()
_CONTRACT_ID = uuid4()
_SNAPSHOT_ID = uuid4()
_LISTING_ID = uuid4()


def _signals() -> list[dict[str, object]]:
    return [
        {
            "signal": "cafe_lifestyle",
            "value": 0.4,
            "normalized_value": 0.9,
            "normalization_scope": "barrio",
            "confidence": 0.8,
            "missing": False,
            "contributors": [{"term": "cafe.count_300m", "score": 1.0}],
        }
    ]


def test_present_signal_produces_observed_observation_with_evidence() -> None:
    observations = observations_for_signal(
        listing_id=_LISTING_ID,
        signals=_signals(),
        concepts={"proximidad_cafes": "cafe_lifestyle"},
        contract_version_id=_CONTRACT_ID,
        extraction_version_id=_EXTRACTION_ID,
        snapshot_id=_SNAPSHOT_ID,
        created_at=utcnow(),
        correlation_id=_CID,
    )

    assert len(observations) == 1
    obs = observations[0]
    assert obs.concept_key == "proximidad_cafes"
    assert obs.matcher_type == "signal_score"
    assert obs.source == "urban"
    assert obs.state == "active"
    assert obs.score == 0.9
    assert obs.confidence == 0.8
    assert obs.value == 0.9
    assert obs.evidence["signal_ref"] == "cafe_lifestyle"
    assert obs.evidence["contract_version_id"] == str(_CONTRACT_ID)
    assert obs.evidence["snapshot_id"] == str(_SNAPSHOT_ID)
    contributors = obs.evidence["contributors"]
    assert isinstance(contributors, list) and contributors
    assert contributors[0]["term"] == "cafe.count_300m"


def test_missing_signal_produces_explicit_failed_observation() -> None:
    observations = observations_for_signal(
        listing_id=_LISTING_ID,
        signals=[],
        concepts={"proximidad_cafes": "cafe_lifestyle"},
        contract_version_id=_CONTRACT_ID,
        extraction_version_id=_EXTRACTION_ID,
        snapshot_id=_SNAPSHOT_ID,
        created_at=utcnow(),
        correlation_id=_CID,
    )

    assert len(observations) == 1
    obs = observations[0]
    assert obs.state == "failed"
    assert obs.failure_code == "criteria.urban_unavailable"
    assert obs.score == 0.0
    assert obs.confidence == 0.0
    assert obs.value is None


def test_each_signal_ref_concept_produces_one_observation() -> None:
    observations = observations_for_signal(
        listing_id=_LISTING_ID,
        signals=_signals(),
        concepts={
            "proximidad_cafes": "cafe_lifestyle",
            "acceso_transporte": "transit_access",
        },
        contract_version_id=_CONTRACT_ID,
        extraction_version_id=_EXTRACTION_ID,
        snapshot_id=_SNAPSHOT_ID,
        created_at=utcnow(),
        correlation_id=_CID,
    )

    by_concept = {obs.concept_key: obs for obs in observations}
    assert by_concept["proximidad_cafes"].state == "active"
    assert by_concept["acceso_transporte"].state == "failed"
