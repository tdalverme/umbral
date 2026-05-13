from umbral.models.user import HardFilters, SoftPreferences, UserPreferences
from umbral.scoring import ScoringEngine


def _preferences(**hard_overrides):
    hard = {
        "operation_type": "alquiler",
        "max_price_usd": 900,
        "neighborhoods": ["Palermo"],
        "min_rooms": 2,
        "max_rooms": 3,
        "requires_balcony": True,
    }
    hard.update(hard_overrides)
    return UserPreferences(
        hard_filters=HardFilters(**hard),
        soft_preferences=SoftPreferences(
            weight_luminosity=0.9,
            weight_quietness=0.8,
            weight_wfh_suitability=0.9,
        ),
    )


def _listing(**overrides):
    listing = {
        "id": "analyzed-1",
        "operation_type": "alquiler",
        "price_usd": 780,
        "price_per_m2_usd": 18,
        "quality_score": 88,
        "neighborhood": "Palermo",
        "rooms": 2,
        "raw_features": {"has_balcony": True, "is_pet_friendly": True},
        "scores": {
            "quietness": 0.8,
            "luminosity": 0.9,
            "connectivity": 0.8,
            "wfh_suitability": 0.9,
            "modernity": 0.7,
            "green_spaces": 0.6,
        },
    }
    listing.update(overrides)
    return listing


def test_scoring_engine_scores_excellent_property_high():
    result = ScoringEngine(exchange_rate=1000).score(_listing(), _preferences())

    assert result.eligible is True
    assert result.final_score >= 75
    assert result.criteria
    assert result.band in {"strong", "excellent"}


def test_scoring_engine_rejects_hard_filter_mismatch():
    result = ScoringEngine(exchange_rate=1000).score(
        _listing(price_usd=1200),
        _preferences(max_price_usd=900),
    )

    assert result.eligible is False
    assert result.band == "ineligible"
    assert result.gaps


def test_scoring_engine_tolerates_missing_embeddings():
    result = ScoringEngine(exchange_rate=1000).score(
        _listing(vibe_embedding=None, embedding_vector=None),
        _preferences(),
        preference_vector=[0.1, 0.2, 0.3],
    )

    semantic = [c for c in result.criteria if c.name == "Semantic/vibe fit"][0]
    assert semantic.score == 55
    assert result.eligible is True


def test_scoring_engine_penalizes_repeated_too_expensive_dislikes_near_budget():
    listing = _listing(price_usd=870)
    preferences = _preferences(max_price_usd=900)

    baseline = ScoringEngine(exchange_rate=1000).score(listing, preferences)
    penalized = ScoringEngine(exchange_rate=1000).score(
        listing,
        preferences,
        feedback_examples=[
            {"feedback_type": "dislike", "reason": "too_expensive"},
            {"feedback_type": "dislike", "reason": "too_expensive"},
        ],
    )

    assert penalized.final_score < baseline.final_score
    feedback = [c for c in penalized.criteria if c.name == "Feedback adjustment"][0]
    assert "precio" in feedback.reason.lower()


def test_scoring_engine_ignores_already_seen_as_preference_signal():
    listing = _listing()
    preferences = _preferences()

    baseline = ScoringEngine(exchange_rate=1000).score(listing, preferences)
    already_seen = ScoringEngine(exchange_rate=1000).score(
        listing,
        preferences,
        feedback_examples=[
            {"feedback_type": "dislike", "reason": "already_seen"},
            {"feedback_type": "dislike", "reason": "already_seen"},
        ],
    )

    assert already_seen.final_score == baseline.final_score


def test_scoring_result_fallback_analysis_uses_concrete_points():
    result = ScoringEngine(exchange_rate=1000).score(
        _listing(price_usd=870),
        _preferences(max_price_usd=900),
    )

    analysis = result.to_personalized_analysis()

    assert analysis["why_match"] != result.summary
    assert "Publicacion completa" in analysis["why_match"]
    assert analysis["warnings"]
