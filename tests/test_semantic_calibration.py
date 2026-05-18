from umbral.matching.engine import MatchingService
from umbral.scoring.semantic import SemanticCalibrator


def test_semantic_calibrator_boosts_high_percentile_when_absolute_similarity_is_good():
    calibration = SemanticCalibrator(min_candidates=5).calibrate(
        {
            "low": 0.42,
            "mid": 0.58,
            "top": 0.78,
            "other-1": 0.50,
            "other-2": 0.62,
        }
    )

    assert calibration["top"]["score"] > calibration["mid"]["score"]
    assert calibration["top"]["score"] >= 85
    assert calibration["top"]["metadata"]["percentile"] == 1.0
    assert calibration["top"]["metadata"]["calibration"] == "pool_percentile_v1"


def test_semantic_calibrator_caps_top_score_when_all_absolute_similarities_are_low():
    calibration = SemanticCalibrator(min_candidates=5).calibrate(
        {
            "a": 0.10,
            "b": 0.12,
            "c": 0.14,
            "d": 0.16,
            "top": 0.20,
        }
    )

    assert calibration["top"]["metadata"]["percentile"] == 1.0
    assert calibration["top"]["score"] < 75


def test_semantic_calibrator_does_not_exaggerate_flat_distributions():
    calibration = SemanticCalibrator(min_candidates=5).calibrate(
        {
            "a": 0.700,
            "b": 0.705,
            "c": 0.710,
            "d": 0.715,
            "top": 0.720,
        }
    )

    assert calibration["top"]["metadata"]["calibration"] == "flat_distribution_v1"
    assert calibration["top"]["score"] - calibration["a"]["score"] <= 3


def test_semantic_calibrator_uses_small_pool_fallback_for_too_few_candidates():
    calibration = SemanticCalibrator(min_candidates=5).calibrate(
        {
            "a": 0.72,
            "b": 0.74,
        }
    )

    assert calibration["b"]["metadata"]["calibration"] == "small_pool_absolute_v1"
    assert "percentile" not in calibration["b"]["metadata"]


def test_matching_service_builds_semantic_calibration_from_candidate_pool():
    candidates = [
        {"id": "a", "vibe_embedding": [1.0, 0.0]},
        {"id": "b", "vibe_embedding": [0.8, 0.2]},
        {"id": "c", "vibe_embedding": [0.0, 1.0]},
    ]

    calibration = MatchingService()._semantic_calibration(
        candidates,
        preference_vector=[1.0, 0.0],
        min_candidates=3,
    )

    assert calibration["a"]["score"] > calibration["c"]["score"]
    assert calibration["a"]["metadata"]["candidate_count"] == 3
