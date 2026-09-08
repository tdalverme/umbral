"""End-to-end narrative regressions for contract-shaped observations."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from tests.support.radar import build_listing, build_profile
from tests.support.scoring import (
    MATCHER_TYPES,
    SEED,
    TEMPLATES,
    build_compilation,
    build_criterion,
)
from tests.unit.infrastructure.scoring.test_narrative_writer import (
    ScriptedGateway,
    _writer,
)

from umbral.application.criteria.contracts import ListingObservation
from umbral.application.scoring.engine import score_candidates
from umbral.application.scoring.explanations import build_explanation
from umbral.application.scoring.narrative import (
    build_narrative_context,
    deterministic_narrative,
    narrative_label,
)
from umbral.application.scoring.policy import parse_policy_document
from umbral.application.urban.calculator import UrbanSignalCalculator
from umbral.application.urban.contract import load_urban_contract
from umbral.application.urban.observations import (
    UrbanSignalObservationInput,
    build_observation,
)

ROOT = Path(__file__).resolve().parents[4]
CONTRACT_PATH = ROOT / "contracts" / "urban" / "v2" / "urban-contract-v2.json"


def _urban_observation(
    *,
    listing_id: UUID,
    concept_key: str,
    signal_ref: str,
    result: Any,
) -> ListingObservation:
    measured = result.for_signal(signal_ref)
    assert measured is not None
    now = datetime.now(timezone.utc)
    return build_observation(
        listing_id=listing_id,
        input_=UrbanSignalObservationInput(
            concept_key=concept_key,
            signal_ref=signal_ref,
            value=measured.value,
            score=measured.value,
            confidence=measured.confidence,
            missing=measured.missing,
            contributors=measured.contributors,
            extraction_version_id=uuid4(),
            created_at=now,
            correlation_id=uuid4(),
        ),
        contract_version_id=uuid4(),
        snapshot_id=uuid4(),
    )


def _narrative_for_observation(
    *,
    concept_key: str,
    polarity: str,
    observation: ListingObservation,
    matcher_type: str = "signal_score",
) -> tuple[Any, Any, Any]:
    policy = parse_policy_document(SEED, MATCHER_TYPES)
    profile = build_profile()
    listing = build_listing(listing_id=observation.listing_id)
    run_id = uuid4()
    profile_version_id = uuid4()
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=profile_version_id,
        criteria=(
            build_criterion(
                concept_key,
                matcher_type=matcher_type,
                params={"polarity": polarity},
                weight=1.0,
            ),
        ),
    )
    candidate = score_candidates(
        profile=profile,
        compilation=compilation,
        candidates=(listing,),
        observations={listing.listing_id: {concept_key: observation}},
        policy=policy,
        run_id=run_id,
        correlation_id=uuid4(),
        now=datetime.now(timezone.utc),
    )[0]
    evaluation = next(
        item for item in candidate.evaluations if item.criterion_key == concept_key
    )
    explanation = build_explanation(
        search_profile_id=profile.profile_id,
        run_id=run_id,
        listing_id=listing.listing_id,
        score=candidate.score,
        confidence=candidate.confidence,
        evaluations=(evaluation,),
        policy=policy,
        templates=TEMPLATES,
        satisfied_filters=(),
        profile_version_id=profile_version_id,
    )
    context = build_narrative_context(
        explanation=explanation,
        listing=candidate.narrative_listing,
        active_criteria={
            concept_key: {
                "label": narrative_label(concept_key),
                "polarity": polarity,
            }
        },
        observations={concept_key: observation},
    )
    fallback = deterministic_narrative(context)
    gateway = ScriptedGateway()
    gateway.output = {
        "text": fallback.text,
        "used_criteria": list(fallback.used_criteria),
        "used_evidence_refs": list(fallback.used_evidence_refs),
    }
    managed = _writer(gateway).write(context)
    return context, fallback, managed


def test_v2_zero_presence_does_not_survive_as_a_favorable_reason() -> None:
    calculator = UrbanSignalCalculator(load_urban_contract(CONTRACT_PATH))
    result = calculator.calculate(
        poi_distances={
            "supermarket": {"count_600m": [2000.0]},
            "pharmacy": {"count_600m": [2000.0]},
            "convenience": {"count_600m": [2000.0]},
            "health": {"count_600m": [2000.0]},
        }
    )
    listing = build_listing()
    observation = _urban_observation(
        listing_id=listing.listing_id,
        concept_key="proximidad_compras",
        signal_ref="daily_convenience",
        result=result,
    )
    context, fallback, managed = _narrative_for_observation(
        concept_key="proximidad_compras",
        polarity="positive",
        observation=observation,
    )

    daily = result.for_signal("daily_convenience")
    assert daily is not None and daily.value == 0.0
    assert context.geography == ()
    assert context.reasons == ()
    assert "servicios cotidianos cerca" not in fallback.text
    assert managed.source == "deterministic_fallback"


def test_v2_nightlife_without_places_does_not_survive_as_a_favorable_reason() -> None:
    calculator = UrbanSignalCalculator(load_urban_contract(CONTRACT_PATH))
    result = calculator.calculate(
        poi_distances={
            "nightlife": {
                "count_300m": [2000.0],
                "nearest_m": [2000.0],
            }
        }
    )
    observation = _urban_observation(
        listing_id=uuid4(),
        concept_key="vida_nocturna",
        signal_ref="nightlife_intensity",
        result=result,
    )

    context, fallback, managed = _narrative_for_observation(
        concept_key="vida_nocturna",
        polarity="positive",
        observation=observation,
    )

    nightlife = result.for_signal("nightlife_intensity")
    assert nightlife is not None and nightlife.value == 0.0
    assert context.geography == ()
    assert context.reasons == ()
    assert "actividad nocturna" not in fallback.text
    assert managed.source == "deterministic_fallback"


def test_v2_road_noise_applies_user_polarity_once() -> None:
    calculator = UrbanSignalCalculator(load_urban_contract(CONTRACT_PATH))
    far = calculator.calculate(
        linear_distances={
            "major_road": {"nearest_m": [500.0]},
            "highway": {"nearest_m": [500.0]},
        }
    )
    near = calculator.calculate(
        linear_distances={
            "major_road": {"nearest_m": [40.0]},
            "highway": {"nearest_m": [40.0]},
        }
    )

    far_context, _, _ = _narrative_for_observation(
        concept_key="ruido_transito",
        polarity="negative",
        observation=_urban_observation(
            listing_id=uuid4(),
            concept_key="ruido_transito",
            signal_ref="road_noise",
            result=far,
        ),
    )
    near_context, _, _ = _narrative_for_observation(
        concept_key="ruido_transito",
        polarity="negative",
        observation=_urban_observation(
            listing_id=uuid4(),
            concept_key="ruido_transito",
            signal_ref="road_noise",
            result=near,
        ),
    )
    far_positive, _, _ = _narrative_for_observation(
        concept_key="ruido_transito",
        polarity="positive",
        observation=_urban_observation(
            listing_id=uuid4(),
            concept_key="ruido_transito",
            signal_ref="road_noise",
            result=far,
        ),
    )
    near_positive, _, _ = _narrative_for_observation(
        concept_key="ruido_transito",
        polarity="positive",
        observation=_urban_observation(
            listing_id=uuid4(),
            concept_key="ruido_transito",
            signal_ref="road_noise",
            result=near,
        ),
    )

    far_noise = far.for_signal("road_noise")
    near_noise = near.for_signal("road_noise")
    assert far_noise is not None and far_noise.value == 0.0
    assert near_noise is not None and near_noise.value == 1.0
    assert [fact.value for fact in far_context.geography] == [
        "alejada de los principales corredores"
    ]
    assert [item["fact"] for item in near_context.tradeoffs] == [
        "con una avenida principal relativamente cerca"
    ]
    assert [item["fact"] for item in far_positive.tradeoffs] == [
        "alejada de los principales corredores"
    ]
    assert [fact.value for fact in near_positive.geography] == [
        "con una avenida principal relativamente cerca"
    ]


def test_contract_enum_values_keep_negative_non_geographic_direction() -> None:
    cases = (
        ("luminosidad", "baja", "poca luz natural", "buena luz natural"),
        ("estado_general", "malo", "estado general deteriorado", "buen estado general"),
    )

    for concept_key, value, expected, forbidden in cases:
        listing = build_listing()
        observation = ListingObservation(
            observation_id=uuid4(),
            listing_id=listing.listing_id,
            concept_key=concept_key,
            matcher_type="semantic_feature",
            value=value,
            score=0.1,
            confidence=0.9,
            evidence={},
            source="model",
            extraction_version_id=None,
            state="active",
            failure_code=None,
            recomputation_run_id=None,
            created_at=datetime.now(timezone.utc),
            correlation_id=uuid4(),
        )
        context, fallback, managed = _narrative_for_observation(
            concept_key=concept_key,
            polarity="negative",
            observation=observation,
            matcher_type="semantic_feature",
        )

        assert expected in fallback.text
        assert forbidden not in fallback.text
        assert forbidden not in managed.text


def test_contract_enum_values_keep_positive_non_geographic_direction() -> None:
    cases = (
        ("luminosidad", "alta", "buena luz natural"),
        ("estado_general", "bueno", "buen estado general"),
    )

    for concept_key, value, expected in cases:
        listing = build_listing()
        observation = ListingObservation(
            observation_id=uuid4(),
            listing_id=listing.listing_id,
            concept_key=concept_key,
            matcher_type="semantic_feature",
            value=value,
            score=0.9,
            confidence=0.9,
            evidence={},
            source="model",
            extraction_version_id=None,
            state="active",
            failure_code=None,
            recomputation_run_id=None,
            created_at=datetime.now(timezone.utc),
            correlation_id=uuid4(),
        )

        _, fallback, managed = _narrative_for_observation(
            concept_key=concept_key,
            polarity="positive",
            observation=observation,
            matcher_type="semantic_feature",
        )

        assert expected in fallback.text
        assert expected in managed.text
