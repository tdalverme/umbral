from umbral.models.user import HardFilters, SoftPreferences, UserPreferences
from umbral.scoring import SCORING_VERSION, ScoringEngine


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
        "urban_signals": {
            "signals": {
                "noise_risk": 0.2,
                "walkability": 0.8,
                "transit_access": 0.7,
                "green_access": 0.6,
                "nightlife_intensity": 0.2,
                "daily_convenience": 0.9,
                "cafe_lifestyle": 0.5,
                "commercial_intensity": 0.4,
                "residential_calm": 0.7,
                "confidence": 0.9,
            }
        },
    }
    listing.update(overrides)
    return listing


def _urban_signals(**overrides):
    signals = {
        "noise_risk": 0.2,
        "walkability": 0.8,
        "transit_access": 0.7,
        "green_access": 0.6,
        "nightlife_intensity": 0.2,
        "daily_convenience": 0.9,
        "cafe_lifestyle": 0.5,
        "commercial_intensity": 0.4,
        "residential_calm": 0.7,
        "confidence": 0.9,
        "contributors": [{"type": "subway", "distance_m": 500}],
    }
    signals.update(overrides)
    return {"signals": signals, "computed_version": "urban_signals_v1"}


def test_scoring_engine_scores_excellent_property_high():
    result = ScoringEngine(exchange_rate=1000).score(_listing(), _preferences())

    assert result.eligible is True
    assert result.final_score >= 75
    assert result.criteria
    assert result.band in {"strong", "excellent"}
    assert SCORING_VERSION == "2.0"


def test_scoring_engine_rejects_hard_filter_mismatch():
    result = ScoringEngine(exchange_rate=1000).score(
        _listing(price_usd=1200),
        _preferences(max_price_usd=900),
    )

    assert result.eligible is False
    assert result.band == "ineligible"
    assert result.gaps


def test_scoring_engine_uses_total_monthly_cost_for_rent_budget():
    result = ScoringEngine(exchange_rate=1000).score(
        _listing(
            price_usd=780,
            maintenance_fee_usd=180,
            total_monthly_cost_usd=960,
        ),
        _preferences(max_price_usd=850),
    )

    assert result.eligible is True
    cost = [c for c in result.criteria if c.name == "Cost fit"][0]
    assert cost.score < 58
    assert "costo total" in cost.reason.lower()


def test_scoring_engine_rejects_size_below_minimum():
    result = ScoringEngine(exchange_rate=1000).score(
        _listing(size_covered_m2=32, size_total_m2=35),
        _preferences(min_size_m2=40),
    )

    assert result.eligible is False
    assert any("superficie" in gap.lower() for gap in result.gaps)


def test_scoring_engine_tolerates_missing_urban_signals_with_low_confidence_warning():
    result = ScoringEngine(exchange_rate=1000).score(
        _listing(latitude=None, longitude=None, urban_signals=None),
        _preferences(),
    )

    urban = [c for c in result.criteria if c.name == "Urban fit"][0]
    assert urban.score == 50
    assert any("senales urbanas" in gap.lower() for gap in result.gaps)


def test_scoring_engine_noise_penalty_respects_noise_tolerance():
    noisy_listing = _listing(
        urban_signals=_urban_signals(
            noise_risk=0.9,
            walkability=0.8,
            transit_access=0.8,
            residential_calm=0.2,
        )
    )
    quiet_seeker = _preferences()
    quiet_seeker.soft_preferences.noise_tolerance = 0.1
    urban_seeker = _preferences()
    urban_seeker.soft_preferences.noise_tolerance = 0.9

    quiet_score = ScoringEngine(exchange_rate=1000).score(noisy_listing, quiet_seeker)
    urban_score = ScoringEngine(exchange_rate=1000).score(noisy_listing, urban_seeker)

    quiet_urban = [c for c in quiet_score.criteria if c.name == "Urban fit"][0]
    tolerant_urban = [c for c in urban_score.criteria if c.name == "Urban fit"][0]
    assert quiet_urban.score < tolerant_urban.score


def test_scoring_engine_walkability_and_transit_help_without_overriding_bad_cost():
    listing = _listing(
        price_usd=900,
        maintenance_fee_usd=120,
        total_monthly_cost_usd=1020,
        urban_signals=_urban_signals(walkability=0.95, transit_access=0.95),
    )

    result = ScoringEngine(exchange_rate=1000).score(listing, _preferences(max_price_usd=900))

    cost = [c for c in result.criteria if c.name == "Cost fit"][0]
    urban = [c for c in result.criteria if c.name == "Urban fit"][0]
    assert urban.score >= 80
    assert cost.score < 58
    assert result.final_score < 85


def test_scoring_engine_quality_is_confidence_not_desirability_boost():
    low_quality = ScoringEngine(exchange_rate=1000).score(
        _listing(quality_score=45, urban_signals=_urban_signals(confidence=0.4)),
        _preferences(),
    )
    high_quality = ScoringEngine(exchange_rate=1000).score(
        _listing(quality_score=98, urban_signals=_urban_signals(confidence=1.0)),
        _preferences(),
    )

    low_confidence = [c for c in low_quality.criteria if c.name == "Freshness/confidence"][0]
    high_confidence = [c for c in high_quality.criteria if c.name == "Freshness/confidence"][0]
    assert low_confidence.score < 60
    assert high_confidence.score <= 78
    assert high_quality.final_score - low_quality.final_score < 4


def test_scoring_engine_allows_price_within_relaxed_budget_window():
    result = ScoringEngine(exchange_rate=1000).score(
        _listing(price_usd=915),
        _preferences(max_price_usd=800),
    )

    assert result.eligible is True
    price_fit = [c for c in result.criteria if c.name == "Cost fit"][0]
    assert price_fit.score < 68
    assert "sobre tu presupuesto" in price_fit.reason.lower()


def test_scoring_engine_parses_decimal_price_usd_from_database_string():
    result = ScoringEngine(exchange_rate=1000).score(
        _listing(price_usd="824.74"),
        _preferences(max_price_usd=800),
    )

    assert result.eligible is True
    price_fit = [c for c in result.criteria if c.name == "Cost fit"][0]
    assert price_fit.score == 52


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
    baseline_cost = [c for c in baseline.criteria if c.name == "Cost fit"][0]
    penalized_cost = [c for c in penalized.criteria if c.name == "Cost fit"][0]
    assert penalized_cost.score <= baseline_cost.score - 8
    assert "feedback" in penalized_cost.reason.lower()


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
    assert "Ambientes alineados" in analysis["why_match"]
    assert analysis["warnings"]
