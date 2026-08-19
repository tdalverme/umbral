"""The signal_score matcher flows normalized signal scores into scoring."""

from __future__ import annotations

from umbral.application.scoring.evaluators import evaluate_observation_criterion
from umbral.application.scoring.policy import PolicyCriterion

_NONE = object()


def _criterion() -> PolicyCriterion:
    return PolicyCriterion(
        key="proximidad_cafes",
        concept="proximidad_cafes",
        matcher_type="signal_score",
        weight=0.1,
        params={"signal_ref": "cafe_lifestyle"},
        gate=None,
    )


def _negative_criterion() -> PolicyCriterion:
    return PolicyCriterion(
        key="ruido_transito",
        concept="ruido_transito",
        matcher_type="signal_score",
        weight=0.1,
        params={"signal_ref": "road_noise", "polarity": "negative"},
        gate=None,
    )


def test_high_signal_score_is_a_match_with_full_confidence() -> None:
    criterion = _criterion()
    result = evaluate_observation_criterion(criterion, None, 0.87, 0.95)

    assert result.state == "match"
    assert result.score == 0.87
    assert result.confidence == 0.95
    assert result.reason_code == "signal_observed"


def test_low_signal_score_is_still_an_observed_match() -> None:
    result = evaluate_observation_criterion(_criterion(), None, 0.1, 0.9)

    assert result.state == "match"
    assert result.reason_code == "signal_observed"
    assert result.score == 0.1


def test_missing_signal_stays_unknown() -> None:
    result = evaluate_observation_criterion(_criterion(), None, None, None)

    assert result.state == "unknown"
    assert result.score == 0.0
    assert result.confidence == 0.0
    assert result.reason_code == "no_observation_data"


def test_confidence_is_carried_through() -> None:
    result = evaluate_observation_criterion(_criterion(), None, 0.5, 0.4)

    assert result.confidence == 0.4
    assert result.score == 0.5


def test_negative_polarity_inverts_the_signal_score() -> None:
    result = evaluate_observation_criterion(_negative_criterion(), None, 0.87, 0.95)

    assert result.state == "match"
    assert result.score == round(1.0 - 0.87, 4)
    assert result.confidence == 0.95
    assert result.reason_code == "signal_observed"


def test_negative_polarity_low_noise_scores_high() -> None:
    result = evaluate_observation_criterion(_negative_criterion(), None, 0.1, 0.9)

    assert result.state == "match"
    assert result.score == round(1.0 - 0.1, 4)


def test_negative_polarity_missing_stays_unknown() -> None:
    result = evaluate_observation_criterion(_negative_criterion(), None, None, None)

    assert result.state == "unknown"
    assert result.score == 0.0
    assert result.confidence == 0.0
    assert result.reason_code == "no_observation_data"
